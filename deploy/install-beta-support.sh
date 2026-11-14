#!/usr/bin/env bash
set -euo pipefail
[[ "${EUID}" == 0 ]] || { echo 'Install beta support as root on the target image/Pi.' >&2; exit 1; }
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! id usa-console >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin usa-console
fi
install -m 0755 "${INSTALLER_DIR}/usa-network-console.py" /usr/local/libexec/usa-network-console
install -m 0644 "${INSTALLER_DIR}/usa_network.py" /usr/local/libexec/usa_network.py
install -m 0755 "${INSTALLER_DIR}/beta-diagnostics.py" /usr/local/libexec/usa-beta-diagnostics
install -m 0440 "${INSTALLER_DIR}/usa-console.sudoers" /etc/sudoers.d/usa-console
visudo -cf /etc/sudoers.d/usa-console
install -d -m 0755 /etc/systemd/journald.conf.d /etc/NetworkManager/system-connections
install -m 0644 "${INSTALLER_DIR}/usa-beta-journal.conf" /etc/systemd/journald.conf.d/usa-beta.conf
for unit in usa-network-console.service usa-beta-diagnostics.service usa-beta-diagnostics.timer; do
  install -m 0644 "${INSTALLER_DIR}/${unit}" "/etc/systemd/system/${unit}"
done
# Low priority; NetworkManager never replaces a healthy owner connection.
if [[ ! -f /etc/NetworkManager/system-connections/USA-Ethernet.nmconnection ]]; then
  install -m 0600 "${INSTALLER_DIR}/USA-Ethernet.nmconnection" /etc/NetworkManager/system-connections/USA-Ethernet.nmconnection
fi
systemctl mask getty@tty1.service
systemctl enable usa-network-console.service usa-beta-diagnostics.timer
if [[ "${1:-}" != --image ]]; then
  systemctl daemon-reload
  nmcli connection reload
  systemctl stop getty@tty1.service || true
  systemctl start usa-network-console.service usa-beta-diagnostics.timer
fi
