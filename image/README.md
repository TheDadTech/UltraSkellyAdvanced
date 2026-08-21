# UltraSkellyAdvanced SD image

This directory builds a clean Raspberry Pi OS Lite 64-bit image. It never
clones a development SD card. The build context uses a source whitelist, and
the resulting installation starts in guided Setup mode with motors and DAC
output disarmed. First boot creates a setup hotspot and guides the owner through
network choice, disclosure, and prop pairing. The pinned compact Vosk speech model
is included, so camera, microphone, and offline transcription diagnostics work
without a separate model-install command.

## Build host

Use an Ubuntu or Debian Linux computer with Docker, Git, at least 40 GB of free
disk space, and a stable internet connection. The builder uses Raspberry Pi's
official `pi-gen` project and its ARM64 branch.

```bash
sudo apt-get update
sudo apt-get install -y docker.io git tar coreutils
sudo usermod -aG docker "$USER"
```

Sign out and back in after adding the Docker group, then run from the project:

```bash
chmod +x image/build-image.sh
./image/build-image.sh --docker
```

The versioned compressed image, SHA-256 checksum, and build-provenance file are
written under `.image-build/pi-gen/deploy/`.

## Flash and first boot

1. Open Raspberry Pi Imager and choose **Use Custom**.
2. Select the generated `.img.xz` file.
3. Flash the card and boot the Pi; Imager WiFi and SSH customization are not required.
4. Join `UltraSkellyAdvanced-Setup` with password `dadtech1`.
5. Open `http://192.168.4.1` if the setup page does not open automatically.
6. Choose home WiFi or offline hotspot operation, accept the disclosure, and pair the prop. Fresh images have no saved Skelly, speaker, DAC,
   cloud credentials, or automatic operating mode.

Cloud accounts are not required for Classic Mode or hardware diagnostics. AI
Mode needs either an owner-supplied Groq key or the optional local Qwen model.
ElevenLabs is optional and is used only when selected for speech.

## Release gate

Before publishing an image:

- Verify its SHA-256 checksum after downloading it from the release host.
- Flash a different SD card rather than the development card.
- Boot once with no Skelly, camera, microphone, DAC, or ESP32 attached.
- Confirm the dashboard opens Setup, scans for props, and keeps motion disarmed.
- Test stock-hardware setup and advanced DAC setup separately.
- Confirm motors and DAC output remain disarmed after every reboot until setup.
- Confirm no `/var/lib/skelly-ai/*.json` files or Bluetooth bonds were inherited.
- Confirm offline microphone transcription works before adding cloud keys.
- Test recovery when Wi-Fi credentials are wrong or unavailable.

The first public image should be labeled **Beta / Pi 4 Model B tested**
until additional Pi models and clean-install paths have been verified.
