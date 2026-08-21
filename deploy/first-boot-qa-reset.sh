#!/usr/bin/env bash
set -euo pipefail

echo "This resets USA onboarding, saved keys, WiFi, and Bluetooth pairings."
echo "The Pi will reboot into the UltraSkellyAdvanced-Setup hotspot."
read -r -p "Type RESET to continue: " confirmation
if [[ "${confirmation}" != "RESET" ]]; then
  echo "Reset cancelled."
  exit 1
fi

sudo /usr/local/libexec/usa-system-helper first-boot-reset
echo "First-boot reset scheduled. The current connection will close."
