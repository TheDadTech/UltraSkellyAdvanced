# UltraSkellyAdvanced (USA)

Self-hosted Raspberry Pi software that adds AI conversation, live operator
control, and optional show integration to Home Depot Ultra Skelly and Lethal
Lily animatronics.

The Raspberry Pi keeps the prop connection, Bluetooth speaker routing, camera,
microphone, safety state, and owner settings local. Cloud AI and voice services
are optional and use API keys supplied by the owner.

## Operating modes

- **Classic Mode** plays and edits the media already stored inside Skelly.
- **AI Mode (unmanned)** detects visitors, listens, answers, selects eyes and
  movement, and continues the conversation while a visitor remains present.
- **Operator Mode (manned)** lets an operator type exact dialogue, monitor the
  visitor camera and microphone, select eyes and lights, and trigger movement.
- **FPP/xLights override (optional)** is available only for the Advanced
  DAC + ESP32 hardware profile and temporarily gives show playback priority.

## Hardware profiles

- **Standard:** stock prop plus Raspberry Pi. BLE controls all 18 eyes, lights,
  and the prop's built-in movement groups. Bluetooth Classic carries speech to
  the built-in speaker.
- **Advanced:** adds the existing DAC + ESP32 installation for exact jaw and
  three-axis head positioning, xLights, and FPP integration.

The raw DAC and FPP controls are hidden when Standard is selected. The built-in
BLE movement Enable/Disable control applies to both profiles; it is separate
from the Advanced DAC interlock.

## Current release features

- First-boot hotspot, WiFi/offline choice, disclosure, and guided BLE pairing
- Persistent connection, speaker, volume, sensor, DAC, and FPP status
- One-click mode startup in the required safety order
- All 18 factory eye icons and live head/torso lighting controls
- Classic media listing, playback, upload, enable/disable, and preset editing
- Local face/person/motion detection and offline Vosk transcription
- Local Qwen 2.5 brain or Groq GPT-OSS 20B cloud brain
- Local eSpeak, Groq Orpheus, or ElevenLabs text-to-speech
- Very quiet Bluetooth wake signal that protects the first spoken word across
  all voice providers
- Adjustable speech speed, output volume, and DAC jaw activity
- Owner credentials stored only on the Pi with mode `0600`
- Automatic local fallback when a selected cloud service is unavailable
- Developer-only raw BLE probes disabled in public installations
- Automatic read-only update check with a visible availability badge
- Clean Raspberry Pi image definition with SHA-256 output checksums

## Install on Raspberry Pi OS

Use Raspberry Pi OS Lite 64-bit on a Pi 4. Pi 5 should also work, but the public
image release should be verified on both models before it is advertised as
supported.

```bash
chmod +x deploy/bootstrap-pi.sh
./deploy/bootstrap-pi.sh
```

Open `http://<pi-hostname>:8787` from a device on the same network. If the local
hostname is not resolved by the router, use the Pi's IP address.

The optional offline speech model is installed with:

```bash
chmod +x deploy/install-speech-model.sh
./deploy/install-speech-model.sh
```

The optional local Qwen brain is installed with:

```bash
chmod +x deploy/install-local-brain.sh
./deploy/install-local-brain.sh
```

## Public SD image

The image builder in `image/` uses Raspberry Pi's official ARM64 `pi-gen` base.
It builds from source and never clones a development card, saved credentials,
Bluetooth pairings, media history, or network-specific DAC targets.

Fresh images start hotspot `UltraSkellyAdvanced-Setup` with password
`dadtech1`. The owner may join home WiFi or keep the controller offline on that
hotspot. SSH is disabled; Diagnostics can enable user `dadtech` with a new private
password for 30 minutes or until explicitly disabled.

Build the image on Ubuntu:

```bash
cd image
./build-image.sh --docker
```

Publish the compressed image and its generated `.sha256` file together. Follow
the clean-card release gate in `image/README.md` before public distribution.

## Voice services

The presets are deliberately simple:

- **Fully Offline:** local Qwen + local eSpeak; no cloud quota
- **Cloud Starter:** Groq GPT-OSS 20B + Groq Orpheus; account limits apply
- **Best Voice:** Groq GPT-OSS 20B + ElevenLabs; provider credits may be used

Groq and ElevenLabs plans and limits can change, so the interface does not
promise that a cloud option is permanently free. Voice previews and spoken
responses can consume provider quota.

ElevenLabs integration uses a Voice ID for text-to-speech. An ElevenLabs Agent
ID is not required. The project signup link is the owner's disclosed affiliate
link; no separate affiliate-program link is shown.

Credential changes are accepted from the controller's local network, so a
regular owner can use **Validate and save** without SSH. Keys are never returned
by the API or included in diagnostics.

## Bluetooth speaker wake-up

Some Skelly speakers clip the first word while the Bluetooth audio transport
wakes. The Voice Tuning slider sends a very quiet tone before the sentence,
instead of silence or a fake spoken word. The same path is used by local,
Groq, and ElevenLabs voices. The separate Bluetooth delay setting only aligns
Advanced DAC jaw animation with audible speech.

## FPP endpoints

```text
POST /api/show/start   JSON: {"name":"Sequence name"}
POST /api/show/end
GET  /api/status
```

FPP override must be enabled under the Advanced hardware profile. If
`SKELLY_FPP_TOKEN` is configured, send it in the `X-Skelly-Token` header.

## Update manifest

Set `SKELLY_UPDATE_MANIFEST_URL` to an HTTPS JSON document shaped like:

```json
{
  "version": "0.25.0",
  "download_url": "https://github.com/TheDadTech/UltraSkellyAdvanced/releases/tag/v0.25.0",
  "release_notes_url": "https://github.com/TheDadTech/UltraSkellyAdvanced/releases/tag/v0.25.0"
}
```

The dashboard can then check and link to the release. Installation remains
manual until signed-package verification, settings preservation, restart
feedback, and rollback have been completed and tested.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
skelly-ai
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` and open
`http://localhost:8787`.

Set `SKELLY_DEVELOPER_MODE=true` only on a controlled development Pi to expose
the raw BLE movement probe. Public images default it to false.
