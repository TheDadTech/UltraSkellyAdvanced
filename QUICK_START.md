# UltraSkellyAdvanced 0.25.4 beta quick start

## What you need

- Raspberry Pi 4 Model B (4 GB recommended)
- 16 GB or larger microSD card
- Home Depot Ultra Skelly or Lethal Lily
- USB camera with microphone for AI Mode
- A phone, tablet, or computer with WiFi

The beta image is validated for Raspberry Pi 4 Model B. Pi 3 and Pi 5 are not
yet in the supported test matrix.

## Flash and connect

1. In Raspberry Pi Imager, choose **Use Custom** and select the USA `.img.xz`.
2. Flash the card, insert it into the Pi, and power it on. Imager WiFi settings
   are not required; first boot intentionally starts the setup hotspot.
3. Connect to the **UltraSkellyAdvanced-Setup** WiFi network using password
   **`dadtech1`**.
4. Open `http://192.168.4.1` if the setup page does not open automatically.
5. Choose a home WiFi network or select **Remain on USA hotspot** for offline use.
6. Review and accept the safety disclosure, then power on and pair the prop.

After joining home WiFi, reopen `http://usa-controller:8787`. If hostnames are
unavailable, use the address shown by the router. SSH is disabled and
is not needed for setup or operation. A private, temporary support login can be
enabled later from Diagnostics.

## Services and safety

Classic Mode, Operator Mode, local sensors, and offline speech do not require a
paid service. Groq and ElevenLabs remain optional owner-configured services;
their keys and usage are never included in the image.

Keep people, pets, hair, clothing, and cables clear of every moving joint.
Motion, DAC output, and FPP override begin disabled. Use Stop and shut down the
Pi from Diagnostics whenever behavior is unexpected.

## First-boot QA on the development Pi

Before building another SD image, install the candidate on the Pi and run:

```bash
cd ~/skelly-ai
bash ./deploy/first-boot-preflight.sh
bash ./deploy/first-boot-qa-reset.sh
```

The reset removes USA settings, saved cloud keys, home WiFi, and Bluetooth
pairings, disables SSH, and reboots into `UltraSkellyAdvanced-Setup`. Reconnect
with password `dadtech1` and test the same workflow a new owner will receive.
Only build a distributable image after this test passes.
