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

# Allow the headless WirePlumber session to expose paired Bluetooth audio
# devices even though there is no desktop login seat.
sudo install -d -m 0755 -o "${SKELLY_USER}" -g "${SKELLY_GROUP}" "${SKELLY_HOME}/.config/wireplumber/wireplumber.conf.d"
sudo tee "${SKELLY_HOME}/.config/wireplumber/wireplumber.conf.d/50-headless-bluetooth.conf" >/dev/null <<'EOF'
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
sudo chown -R "${SKELLY_USER}:${SKELLY_GROUP}" "${SKELLY_HOME}/.config"

# Headless audio services need a persistent user runtime directory. Add the
# installing user to whichever hardware-access groups exist on this image.
for hardware_group in audio video render plugdev bluetooth; do
  if getent group "${hardware_group}" >/dev/null; then
    sudo usermod -aG "${hardware_group}" "${SKELLY_USER}"
  fi
done
sudo loginctl enable-linger "${SKELLY_USER}"

sudo install -d -m 0755 /opt/skelly-ai
sudo install -d -m 0755 /usr/local/libexec
sudo install -d -m 0700 -o "${SKELLY_USER}" -g "${SKELLY_GROUP}" /var/lib/skelly-ai
sudo python3 -m venv /opt/skelly-ai/venv
sudo /opt/skelly-ai/venv/bin/pip install --upgrade pip
sudo /opt/skelly-ai/venv/bin/pip install --upgrade --no-cache-dir "${PROJECT_DIR}"
if ! id dadtech >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash dadtech
  sudo passwd --lock dadtech
fi
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
# `enable --now` does not restart an already-running service during an update.
# Restart explicitly so the new Python package and dashboard are loaded now.
sudo systemctl restart skelly-ai

# Raspberry Pi OS Lite does not start a desktop audio session. Start the
# dedicated service user's manager, enable its audio stack, and restart
# WirePlumber so the headless Bluetooth fragment is loaded on upgrades too.
sudo systemctl start "user@${SKELLY_UID}.service"
sudo -u "${SKELLY_USER}" env XDG_RUNTIME_DIR="/run/user/${SKELLY_UID}" \
  systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service 2>/dev/null || true
sudo -u "${SKELLY_USER}" env XDG_RUNTIME_DIR="/run/user/${SKELLY_UID}" \
  systemctl --user restart pipewire.service wireplumber.service 2>/dev/null || true

echo
PI_ADDRESS="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo "UltraSkellyAdvanced is installed."
echo "Try: http://$(hostname):8787"
if [[ -n "${PI_ADDRESS}" ]]; then
  echo "IP fallback: http://${PI_ADDRESS}:8787"
fi
echo "Service status: sudo systemctl status skelly-ai"
echo "Live logs: sudo journalctl -u skelly-ai -f"
