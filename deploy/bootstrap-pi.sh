#!/usr/bin/env bash
set -euo pipefail
if [[ "${EUID}" -eq 0 && "${USA_UPDATE_INSTALL:-0}" != "1" ]]; then
  echo "Run this script as the normal Pi user; it will use sudo when required." >&2
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLING_USER="${USA_INSTALLING_USER:-$(id -un)}"
if id skelly-ai >/dev/null 2>&1; then
  # Preserve the dedicated service identity used by distributable USA images.
  SKELLY_USER="skelly-ai"
  SKELLY_GROUP="$(id -gn skelly-ai)"
  SKELLY_UID="$(id -u skelly-ai)"
  SKELLY_HOME="$(getent passwd skelly-ai | cut -d: -f6)"
else
  SKELLY_USER="${INSTALLING_USER}"
  SKELLY_GROUP="$(id -gn "${INSTALLING_USER}")"
  SKELLY_UID="$(id -u "${INSTALLING_USER}")"
  SKELLY_HOME="$(getent passwd "${INSTALLING_USER}" | cut -d: -f6)"
fi

SUPPORT_USER="dadtech"
if ! id "${SUPPORT_USER}" >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash "${SUPPORT_USER}"
  sudo passwd --lock "${SUPPORT_USER}"
fi
SUPPORT_GROUP="$(id -gn "${SUPPORT_USER}")"
SUPPORT_UID="$(id -u "${SUPPORT_USER}")"
SUPPORT_HOME="$(getent passwd "${SUPPORT_USER}" | cut -d: -f6)"

sudo apt-get update
sudo apt-get install -y \
  alsa-utils \
  avahi-daemon \
  bluez \
  bluez-firmware \
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

# Both the dedicated USA service identity and the support/login identity may
# exist on an appliance. PipeWire playback is deliberately owned by dadtech,
# so configure that session for headless Bluetooth and make it persistent.
configure_headless_audio_user() {
  local user="$1" group="$2" home="$3"
  sudo install -d -m 0755 -o "${user}" -g "${group}" "${home}/.config/wireplumber/wireplumber.conf.d"
  sudo tee "${home}/.config/wireplumber/wireplumber.conf.d/50-headless-bluetooth.conf" >/dev/null <<'EOF'
wireplumber.profiles = {
  main = {
    monitor.bluez = required
    monitor.bluez.seat-monitoring = disabled
  }
}
monitor.bluez.properties = {
  bluez5.roles = [ a2dp_sink a2dp_source ]
}
EOF
  sudo chown -R "${user}:${group}" "${home}/.config"
  for hardware_group in audio video render plugdev bluetooth; do
    if getent group "${hardware_group}" >/dev/null; then
      sudo usermod -aG "${hardware_group}" "${user}"
    fi
  done
  sudo loginctl enable-linger "${user}"
}

configure_headless_audio_user "${SKELLY_USER}" "${SKELLY_GROUP}" "${SKELLY_HOME}"
if [[ "${SUPPORT_USER}" != "${SKELLY_USER}" ]]; then
  configure_headless_audio_user "${SUPPORT_USER}" "${SUPPORT_GROUP}" "${SUPPORT_HOME}"
fi

sudo install -d -m 0755 /opt/skelly-ai
sudo install -d -m 0755 /usr/local/libexec
sudo install -d -m 0700 -o "${SKELLY_USER}" -g "${SKELLY_GROUP}" /var/lib/skelly-ai
sudo python3 -m venv /opt/skelly-ai/venv
sudo /opt/skelly-ai/venv/bin/pip install --upgrade pip
sudo /opt/skelly-ai/venv/bin/pip install --upgrade --no-cache-dir "${PROJECT_DIR}"
sudo install -m 0755 "${PROJECT_DIR}/deploy/usa-system-helper.py" \
  /usr/local/libexec/usa-system-helper
sudo install -m 0644 "${PROJECT_DIR}/deploy/usa-network.service" \
  /etc/systemd/system/usa-network.service
sudo install -m 0644 "${PROJECT_DIR}/deploy/usa-nginx.conf" \
  /etc/nginx/sites-available/usa
sudo ln -sf /etc/nginx/sites-available/usa /etc/nginx/sites-enabled/usa
sudo rm -f /etc/nginx/sites-enabled/default
sudo install -d -m 0755 /etc/NetworkManager/dnsmasq-shared.d
printf '%s\n' 'address=/#/192.168.4.1' \
  | sudo tee /etc/NetworkManager/dnsmasq-shared.d/usa-captive.conf >/dev/null
{
  printf '%s ALL=(root) NOPASSWD: /usr/local/libexec/usa-system-helper *\n' "${SKELLY_USER}"
  printf '%s ALL=(root) NOPASSWD: /usr/local/libexec/usa-system-helper *\n' dadtech
} | sudo tee /etc/sudoers.d/usa-system-helper >/dev/null
sudo chmod 0440 /etc/sudoers.d/usa-system-helper

sudo install -d -m 0750 -o root -g "${SKELLY_GROUP}" /etc/skelly-ai
if [[ ! -f /etc/skelly-ai/skelly-ai.env ]]; then
  sudo install -m 0640 -o root -g "${SKELLY_GROUP}" \
    "${PROJECT_DIR}/deploy/skelly-ai.env.example" \
    /etc/skelly-ai/skelly-ai.env
fi
# Version 0.25.0 accidentally shipped one developer's custom speaker PIN as
# the product default. Migrate only that exact legacy value; preserve every
# other owner-customized PIN and all unrelated settings during an update.
if sudo grep -qx 'SKELLY_CLASSIC_AUDIO_PIN=0727' /etc/skelly-ai/skelly-ai.env; then
  sudo sed -i \
    's/^SKELLY_CLASSIC_AUDIO_PIN=0727$/SKELLY_CLASSIC_AUDIO_PIN=1234/' \
    /etc/skelly-ai/skelly-ai.env
fi

sed \
  -e "s/@SKELLY_USER@/${SKELLY_USER}/g" \
  -e "s/@SKELLY_GROUP@/${SKELLY_GROUP}/g" \
  -e "s/@SKELLY_UID@/${SKELLY_UID}/g" \
  -e "s|@SKELLY_HOME@|${SKELLY_HOME}|g" \
  -e "s/@SUPPORT_UID@/${SUPPORT_UID}/g" \
  "${PROJECT_DIR}/deploy/skelly-ai.service.in" \
  | sudo tee /etc/systemd/system/skelly-ai.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable --now avahi-daemon bluetooth
sudo systemctl enable --now nginx
# `enable --now` does not reload an already-running nginx instance during an
# update. Restart it so the newly installed USA proxy and captive routes are
# active before preflight runs.
sudo systemctl restart nginx
sudo systemctl enable usa-network
sudo systemctl enable hciuart.service 2>/dev/null || true
sudo systemctl enable skelly-ai

# Raspberry Pi OS Lite has no desktop login to create an audio session. Start
# both user managers now, with dadtech's PipeWire session established before
# USA restarts. Linger keeps the same session available after cold boot.
start_user_audio() {
  local user="$1" uid="$2"
  sudo systemctl start "user@${uid}.service"
  sudo -u "${user}" env \
    XDG_RUNTIME_DIR="/run/user/${uid}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${uid}/bus" \
    systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service 2>/dev/null || true
  sudo -u "${user}" env \
    XDG_RUNTIME_DIR="/run/user/${uid}" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/${uid}/bus" \
    systemctl --user restart pipewire.service wireplumber.service pipewire-pulse.service 2>/dev/null || true
}
start_user_audio "${SKELLY_USER}" "${SKELLY_UID}"
if [[ "${SUPPORT_UID}" != "${SKELLY_UID}" ]]; then
  start_user_audio "${SUPPORT_USER}" "${SUPPORT_UID}"
fi

# `enable --now` does not restart an already-running service during an update.
# Restart explicitly only after the persistent audio session is available.
sudo systemctl restart skelly-ai

echo
PI_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "UltraSkellyAdvanced is installed."
echo "Try: http://$(hostname):8787"
if [[ -n "${PI_ADDRESS}" ]]; then
  echo "IP fallback: http://${PI_ADDRESS}:8787"
fi
echo "Service status: sudo systemctl status skelly-ai"
echo "Live logs: sudo journalctl -u skelly-ai -f"
