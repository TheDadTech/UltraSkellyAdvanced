# UltraSkellyAdvanced 0.25.3 Beta

## Release-blocker corrections

- Real Skelly hardware is now the deployment default; manual upgrades no
  longer fall back to the simulator.
- Speaker preparation now waits up to 30 seconds for the PipeWire Bluetooth
  output, allowing first-boot setup to complete with one button press.
- If the Bluetooth transport completes before its PipeWire output exists,
  USA automatically performs the routing pass that previously required a
  second button click.

This beta incorporates the completed first-boot QA work and the fresh-card
speaker/jaw corrections verified on the Raspberry Pi 4 development hardware.

## Speaker and setup corrections

- Waits for the first-boot PipeWire Bluetooth sink during the initial
  **Prepare and connect speaker** request instead of requiring a second press.
- Selects the Skelly Bluetooth sink and initializes its transport volume to
  100%, restoring the stock controller's audio-reactive jaw response for AI
  and Operator speech. The separate Skelly speaker-volume control remains
  available for listening-level adjustment.
- Labels the BLE status explicitly as **prop connected** or
  **prop disconnected**, separate from speaker status.
- Adds a clickable `usa-controller:8787` continuation link after home WiFi is
  saved.
- Documents the minimum ElevenLabs key permissions: Text to Speech Access,
  Voices Write, and Models Access.
- Restores the factory Live Mode PIN default (`1234`) and retries speaker
  pairing once after removing a stale BlueZ bond.
- Adds a complete in-dashboard updater: HTTPS release download, required
  SHA-256 verification, archive/path and version validation, installation
  progress across the service restart, a post-install health check, and
  automatic application rollback on failure.

# UltraSkellyAdvanced 0.23.4 First-Boot QA Candidate

This candidate is intended for a complete first-user test on the development
Pi before another distributable SD image is built.

## First-boot corrections

- Added a complete QA reset that clears onboarding, credentials, operating
  choices, home WiFi, and Bluetooth bonds before rebooting into setup mode.
- Scans and caches nearby WiFi before starting the Pi's single-radio hotspot.
- Restores the setup hotspot automatically when a home WiFi connection fails.
- Added permanent WiFi management at the bottom of Setup.
- Added standard Apple, Android, Windows, and Firefox captive-portal probes and
  hotspot DNS redirection to the local dashboard.
- Initializes and verifies the onboard Bluetooth adapter before BLE discovery.
- Changed opt-in SSH support to `dadtech@usa-controller`, with the account
  locked whenever SSH is disabled and readable errors instead of tracebacks.

# UltraSkellyAdvanced 0.23.3 Beta

This is the first image-candidate release intended for clean-card testing by
other Ultra Skelly owners.

## Included

- Guided first-run Bluetooth scan and saved-prop setup
- Classic, unmanned AI, and manned Operator modes
- Stock BLE eyes, lighting, and movement groups
- Bluetooth Classic routing to Skelly's internal speaker
- Camera face/person/motion detection and offline microphone transcription
- Optional Groq brain, Groq voice, ElevenLabs voice, or local Qwen brain
- Advanced DAC/ESP32 head, jaw, xLights, and FPP controls
- Safe default state with motors, DAC, and FPP override disabled
- Versioned clean-image builder, checksum, and build-provenance output
- First-boot USA hotspot, WiFi/offline choice, safety disclosure, then pairing
- Header firmware/software pill and automatic nonblocking update notification
- Diagnostics controls for temporary SSH, USA service restart, reboot, and shutdown
- Persistent provider presets with Custom state and reorganized Groq/ElevenLabs setup
- Diagnostics-only software, SSH, and controller power tools
- Reliable selected-state highlighting for AI and voice presets
- Automatic onboard media refresh when Classic Mode starts
- Restored the allowlisted system helper used by first-run WiFi, support access, and controller power
- Added explicit Raspberry Pi WiFi hotspot and onboard Bluetooth firmware/service dependencies
- Added radio unblocking, hardware readiness waits, and useful hotspot activation errors at boot

## Known limitations

- Public image validation currently targets Raspberry Pi 4 Model B.
- Stock BLE exposes movement groups, not exact three-axis head positions.
- Advanced head and jaw positioning requires the DAC/ESP32 installation.
- Bluetooth speaker pairing may require Live Mode to be enabled first.
- Cloud keys are never included. Credential enrollment is available only from
  the USA controller's local network.
- Installing an update requires internet access and a release manifest with a
  direct USA package URL and matching SHA-256 checksum.

## Beta test request

Please report the Pi model/RAM, prop model, camera/microphone, Standard or
Advanced profile, time to first response, and the exact dashboard error text.
Never post API keys, passwords, Bluetooth snoop captures containing personal
devices, or private network details.
