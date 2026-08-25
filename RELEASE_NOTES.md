# UltraSkellyAdvanced 0.25.5 Beta

## Interface and setup cleanup

- Adds a persistent **Help Mode** toggle under Diagnostics. Help Mode can hide explanatory setup text while leaving live status, warnings, and errors visible.
- Makes Local, Groq, and ElevenLabs voice controls reactive to the selected voice provider so only the applicable controls are shown while inactive-provider settings remain saved.
- Collapses configured API-key, Skelly connection, and WiFi setup areas into compact summaries while keeping them available for changes and troubleshooting.
- Moves **Built-in Movement** into the Operator Console, removes the redundant Sensor Diagnostics `no cloud` pill, and clarifies the Standard-mode gesture capability as **No DAC · Laugh Available**.
- Adds versioned frontend asset URLs so browsers, including mobile browsers, fetch updated JavaScript/CSS after an in-app upgrade instead of reusing stale cached assets.

## ElevenLabs voice management

- Loads the saved ElevenLabs account's available voice library into a friendly selector while retaining manual Voice ID entry as a fallback.
- Caches the last successfully loaded ElevenLabs voice list locally so previously discovered voices remain selectable during a temporary provider outage.
- Adds an **ElevenLabs credits remaining** meter to Voice Tuning with green/yellow/red thresholds based on remaining percentage.
- Adds a small, non-intrusive ElevenLabs fuel indicator on Operate when ElevenLabs is the active voice provider.
- Shows an unavailable state instead of falsely displaying zero when ElevenLabs usage cannot be read.
- Updates restricted-key guidance to require Text to Speech Access, Voices Read, Models Access, and User Access for voice-list and remaining-credit features.

## Voice and gesture behavior

- Makes Operator Console **Laugh** use the active Groq or ElevenLabs cloud voice when available, while retaining stored/local audio as the offline or provider-failure fallback.
- Keeps the full ElevenLabs usage meter on Voice Tuning and intentionally does not expose a Groq credit/quota meter.

## Updater safety

- Adds a manual **Roll back to previous version** option when the updater has a verified previous-version backup matching the currently running release.
- Preserves owner configuration, credentials, WiFi settings, character preferences, and other data under `/var/lib/skelly-ai` during rollback.
- Health-checks the restored release before declaring rollback successful.
- Automatically restores the newer working release if the requested rollback fails its health check.
- Does not offer rollback for stale or mismatched backup metadata.

## Validation

- Updater/API/UI focused suite: **47 passed**.
- Browser JavaScript syntax validation is included in the release check after the Stage 2B test checkpoint exposed malformed frontend JavaScript.
- Full project suite: **86 passed, 1 pre-existing Classic Audio test failure**. The same Classic Audio failure predates 0.25.5.

# UltraSkellyAdvanced 0.25.4 Beta

## AI personality and motion

- Adds a persistent **Skelly Name** setting so each installation can give its character a custom name. Existing installations default to **Skelly**.
- Uses the configured Skelly Name in both local-brain and Groq system prompts, and instructs the character to use that name consistently when asked.
- Updates conversation logging to display the configured character name.
- Expands AI motion guidance so conversational replies deliberately vary among head, arm, torso, combined torso/arm, and full-body movement instead of overusing still/limited motion.
- Specifically encourages head and torso motion during ordinary conversation while retaining the existing movement safety/arming checks.
- Leaves Operator Mode and the low-level BLE movement mappings unchanged.

## Validation

- AI brain, cloud-provider, and API targeted tests: **29 passed**.
- Full project suite: **84 passed, 1 pre-existing Classic Audio test failure**. The same Classic Audio failure is present in the unmodified 0.25.3-beta source and is not introduced by this release.

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
