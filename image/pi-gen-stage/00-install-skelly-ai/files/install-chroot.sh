#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  alsa-utils \
  avahi-daemon \
  bluez \
  bluez-firmware \
  ca-certificates \
  curl \
  dnsmasq-base \
  espeak-ng \
  firmware-brcm80211 \
  libspa-0.2-bluetooth \
  network-manager \
  nginx-light \
  openssh-server \
  pi-bluetooth \
  pipewire \
  pipewire-audio \
  python3 \
  python3-pip \
  python3-venv \
  rfkill \
  unzip \
  v4l-utils \
  wireplumber

if ! id skelly-ai >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/skelly-ai \
    --shell /usr/sbin/nologin skelly-ai
fi

# pi-gen creates the public image's first user before this custom stage. Keep a
# defensive fallback so image builds cannot silently omit the support/audio user.
if ! id dadtech >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash dadtech
  passwd --lock dadtech
fi

SKELLY_UID="$(id -u skelly-ai)"
SKELLY_GROUP="$(id -gn skelly-ai)"
SKELLY_HOME="$(getent passwd skelly-ai | cut -d: -f6)"
SUPPORT_UID="$(id -u dadtech)"
SUPPORT_GROUP="$(id -gn dadtech)"
SUPPORT_HOME="$(getent passwd dadtech | cut -d: -f6)"

configure_headless_audio_user() {
  local user="$1" group="$2" home="$3"
  install -d -m 0755 -o "${user}" -g "${group}" \
    "${home}/.config/wireplumber/wireplumber.conf.d"
  cat >"${home}/.config/wireplumber/wireplumber.conf.d/50-headless-bluetooth.conf" <<'CFG'
wireplumber.profiles = {
  main = {
    monitor.bluez = required
    monitor.bluez.seat-monitoring = disabled
  }
}
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_sink a2dp_source ]
}
CFG
  chown -R "${user}:${group}" "${home}/.config"
  for hardware_group in audio video render plugdev bluetooth; do
    if getent group "${hardware_group}" >/dev/null; then
      usermod -aG "${hardware_group}" "${user}"
    fi
  done
}

# 0.25.7+ intentionally uses two independent PipeWire sessions:
#   skelly-ai -> external Bluetooth speech
#   dadtech   -> Animated Skelly(Live) jaw-driving audio
configure_headless_audio_user skelly-ai "${SKELLY_GROUP}" "${SKELLY_HOME}"
configure_headless_audio_user dadtech "${SUPPORT_GROUP}" "${SUPPORT_HOME}"

install -d -m 0755 /opt/skelly-ai
install -d -m 0755 /usr/local/libexec
install -d -m 0755 /etc/NetworkManager/dnsmasq-shared.d
install -d -m 0700 -o skelly-ai -g "${SKELLY_GROUP}" /var/lib/skelly-ai
install -d -m 0750 -o root -g "${SKELLY_GROUP}" /etc/skelly-ai

python3 -m venv /opt/skelly-ai/venv
/opt/skelly-ai/venv/bin/pip install --upgrade pip
/opt/skelly-ai/venv/bin/pip install --no-cache-dir /root/skelly-ai-source.tar.gz

PACKAGE_ROOT="$(mktemp -d)"
tar -xzf /root/skelly-ai-source.tar.gz -C "${PACKAGE_ROOT}"

# Include the small pinned Vosk model so microphone transcription works on the
# first boot without requiring a second terminal-based installation step.
SKELLY_MODEL_ROOT=/var/lib/skelly-ai/models \
  bash "${PACKAGE_ROOT}/deploy/install-speech-model.sh"

# Offline conversation is a core capability of the public image. Install the
# pinned ARM64 llama.cpp runtime and verified Qwen model during the build so a
# fresh SD card works without a separate 1.1 GB post-install download.
SKELLY_BRAIN_IMAGE_INSTALL=1 \
SKELLY_BRAIN_SERVICE_USER=skelly-ai \
  bash "${PACKAGE_ROOT}/deploy/install-local-brain.sh"

install -m 0640 -o root -g "${SKELLY_GROUP}" \
  "${PACKAGE_ROOT}/deploy/skelly-ai.env.example" \
  /etc/skelly-ai/skelly-ai.env
install -m 0755 "${PACKAGE_ROOT}/deploy/usa-system-helper.py" \
  /usr/local/libexec/usa-system-helper
install -m 0644 "${PACKAGE_ROOT}/deploy/usa-network.service" \
  /etc/systemd/system/usa-network.service
install -m 0644 "${PACKAGE_ROOT}/deploy/usa-nginx.conf" \
  /etc/nginx/sites-available/usa
ln -sf /etc/nginx/sites-available/usa /etc/nginx/sites-enabled/usa
rm -f /etc/nginx/sites-enabled/default
cat >/etc/sudoers.d/usa-system-helper <<'SUDOERS'
skelly-ai ALL=(root) NOPASSWD: /usr/local/libexec/usa-system-helper *
dadtech ALL=(root) NOPASSWD: /usr/local/libexec/usa-system-helper *
SUDOERS
chmod 0440 /etc/sudoers.d/usa-system-helper
cat >/etc/NetworkManager/dnsmasq-shared.d/usa-captive.conf <<'DNSMASQ'
# Resolve every setup-hotspot hostname to the local onboarding portal.
address=/#/192.168.4.1
DNSMASQ
raspi-config nonint do_wifi_country US 2>/dev/null || true
# Public images use the real BLE driver but remain disconnected and disarmed
# until the guided first-run scan selects a prop.
sed -i 's/^SKELLY_SIMULATION=true$/SKELLY_SIMULATION=false/' \
  /etc/skelly-ai/skelly-ai.env
sed -i 's/^SKELLY_ONBOARDING_REQUIRED=false$/SKELLY_ONBOARDING_REQUIRED=true/' \
  /etc/skelly-ai/skelly-ai.env
sed \
  -e "s/@SKELLY_USER@/skelly-ai/g" \
  -e "s/@SKELLY_GROUP@/${SKELLY_GROUP}/g" \
  -e "s/@SKELLY_UID@/${SKELLY_UID}/g" \
  -e "s|@SKELLY_HOME@|${SKELLY_HOME}|g" \
  -e "s/@SUPPORT_UID@/${SUPPORT_UID}/g" \
  "${PACKAGE_ROOT}/deploy/skelly-ai.service.in" \
  > /etc/systemd/system/skelly-ai.service

if grep -q '@[A-Z_][A-Z_]*@' /etc/systemd/system/skelly-ai.service; then
  echo "Unresolved placeholder in skelly-ai.service" >&2
  cat /etc/systemd/system/skelly-ai.service >&2
  exit 1
fi
rm -rf "${PACKAGE_ROOT}"

# Both audio owners must have persistent user managers before skelly-ai starts.
install -d -m 0755 /var/lib/systemd/linger
touch /var/lib/systemd/linger/skelly-ai
touch /var/lib/systemd/linger/dadtech
systemctl --global enable pipewire.socket pipewire-pulse.socket 2>/dev/null || true
systemctl --global enable wireplumber.service 2>/dev/null || true
systemctl disable ssh.service 2>/dev/null || true
systemctl enable avahi-daemon.service bluetooth.service hciuart.service nginx.service usa-network.service skelly-ai.service

# The named support account exists for the dashboard's opt-in SSH feature. The
# shared image-build password is locked and SSH remains disabled by default.
usermod --shell /bin/bash --lock dadtech

# The application starts in safe setup mode with no saved hardware,
# credentials, pairings, media history, or network-specific DAC destination.
rm -f /var/lib/skelly-ai/*.json
chown -R skelly-ai:"${SKELLY_GROUP}" /var/lib/skelly-ai
chmod 0700 /var/lib/skelly-ai

apt-get clean
rm -rf /var/lib/apt/lists/*
