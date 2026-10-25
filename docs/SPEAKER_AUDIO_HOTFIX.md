# Speaker audio-session hotfix (0.28.4)

This application update supports installations running USA under a custom Linux
service account. No reflash or new image is required for existing installations.

The application uses its effective service account for Skelly, external speaker,
and playback sessions on custom installs. UID/home/runtime paths are resolved
from the system account database. Managed two-session images retain their existing
Skelly/jaw and external-speaker ownership. The privileged helper authorizes the
service account from the root-owned systemd unit; caller environment variables
cannot grant access to another account. Unrelated user audio sessions are not stopped.

Bluetooth discovery, pairing, trust and connection can proceed if audio-session
preparation fails. Completion still requires the speaker connection and its audio
sink, and the Skelly default route when that output is requested. A later audio
failure reports that pairing succeeded; it is not reported as a completed repair.
BLE prop control and unrelated Bluetooth records remain excluded from repair.

## Existing-install recovery after the hotfix is published

1. Keep the backup/current SD card. Stop AI/Operator/The Lab operation.
2. Install 0.28.4 using System & Tools → USA updates, or the verified Manual ZIP
   update. The updater installs the application **and privileged helper** together.
3. After restart, keep Skelly powered in Live Mode. In Manage Connections, run
   Repair Skelly Speaker and wait for connected/sink-ready status.
4. If uploaded Pi Media should play on Skelly, select Skelly Speaker as the audio
   output in Setup. A selected system/USB output is deliberately not changed by repair.
5. Play one saved clip and verify sound. No credentials need to be re-entered.

A failed speaker repair does not imply the updater is broken: update/rollback
helper actions do not require an audio session. For an independently broken updater,
use the packaged scripts/install-updater-bridge.sh with the verified ZIP, version,
and SHA-256, following the accompanying release/recovery instructions. It validates
before installation and retains a uniquely named recovery backup. It is not a
managed updater rollback entry; preserve that recovery copy and the old card.

Do not create replacement accounts, change UID ownership, copy/delete BlueZ
pairing databases, or alter sudoers as a workaround for audio-account selection.

## Physical verification still required

Test an upgraded custom-account installation with an existing secondary account,
confirm repair and actual audio output, check speaker-only bond changes and BLE
continuity, and test reconnect after reboot. Automated tests simulate BlueZ,
PipeWire and systemd boundaries; they do not constitute physical qualification.
