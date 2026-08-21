#!/usr/bin/env bash
set -euo pipefail

echo "Checking USA candidate before first-boot reset..."
command -v nmcli >/dev/null
command -v bluetoothctl >/dev/null
command -v nginx >/dev/null
test -x /usr/local/libexec/usa-system-helper
test -f /etc/systemd/system/usa-network.service
test -f /etc/NetworkManager/dnsmasq-shared.d/usa-captive.conf
id dadtech >/dev/null
sudo nginx -t
sudo /usr/local/libexec/usa-system-helper bluetooth-prepare >/dev/null
wifi_devices="$(nmcli -t -f DEVICE,TYPE device status)"
grep -q ':wifi$' <<<"${wifi_devices}"
curl --fail --silent http://127.0.0.1:8787/api/health >/dev/null
test "$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1/generate_204)" = "302"

echo "PASS: service, helper, WiFi, Bluetooth, captive portal, and support account are ready."
