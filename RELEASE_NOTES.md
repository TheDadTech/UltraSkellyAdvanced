# UltraSkellyAdvanced 0.26.0-rc1

## Image-readiness polish

- Promotes the personality-mix smoke-tested tree to the first 0.26.0 release candidate.
- Fixes the fresh-image installer so **both** persistent PipeWire/WirePlumber owners are configured: `skelly-ai` for external Bluetooth speech and `dadtech` for stock Skelly jaw audio.
- Fixes the image service-template install to resolve `@SUPPORT_UID@`; the image build now fails if any service placeholder remains unresolved.
- Enables linger for both audio-session users in fresh images so the proven dual-session topology exists after a cold boot without an interactive login.
- Adds `image/release-preflight.sh` to verify version consistency, dual-session image wiring, obvious credential leakage, and the test gate before running pi-gen.
- Expands the image release checklist to explicitly test external speech + jaw + movement across a cold reboot.
- Runtime personality, ElevenLabs WAV playback, external-audio auto-mute, and Bluetooth routing are intentionally unchanged from the smoke-tested dev4 tree.

# UltraSkellyAdvanced 0.26.0-dev4

## Personality pill persistence fix

- Unsaved personality pill selections are no longer overwritten by the 5-second background status refresh.
- Custom personality text is also protected while being edited.
- Normal server-driven rendering resumes immediately after a successful Save Personality action.

Smoke-test build for personality mixing and stronger character differentiation.

- Replaces the personality dropdown with a compact 3x3 glowing-pill selector.
- Classic is selected by default.
- Selecting one personality keeps it fixed; selecting multiple creates a per-response random personality pool.
- Adds Deadpan as the eighth built-in personality; Custom is the ninth pill.
- Custom instructions can participate in a personality mix.
- Strengthens every preset so short responses are visibly more distinct and avoids generic interchangeable skeleton puns.
- Interaction events report the effective personality used for each AI response.
- Retains the 0.26.0-dev2 ElevenLabs WAV playback fix and the proven 0.25.8 dual-session Bluetooth audio stack.

# UltraSkellyAdvanced 0.26.0-dev2

## dev2 smoke-test fix

- Best Voice / ElevenLabs now buffers its PCM response into a WAV before playback instead of piping raw PCM directly to `pw-play`.
- Reuses the same proven dual-session WAV playback path as Cloud Starter, preserving external Bluetooth, Skelly jaw mirror, sync compensation, and movement control.
- Personality behavior remains a brain-layer feature; Operator typed TTS intentionally speaks the text exactly as entered and does not apply personality rewriting.

Personality smoke-test build.

- Adds Classic, Sarcastic, Sinister, Goofy, Grumpy, Friendly, Unhinged, and Custom AI personalities.
- Personality persists on the Pi and applies to both Local Brain and Groq.
- Custom personality is limited to style; USA's identity, safety, concise-response, JSON, and movement-control rules remain authoritative.
- No intentional changes to the proven 0.25.8 Bluetooth, external-audio, jaw-mirror, sync-compensation, or movement-control architecture.

# UltraSkellyAdvanced 0.25.8

## Audio polish / maintenance release

- Adds **Mute Skelly speaker with external audio** (default ON). The prop's BLE speaker volume is set to 0 while the independent full-strength A2DP jaw-mirror stream remains active.
- Remembers the user's prior Skelly speaker volume and restores it when switching back from External Bluetooth. Changes to the header volume while externally muted update the restore value without unmuting Skelly.
- Keeps provider changes hot-applied and re-asserts existing dual-session routing without reconnecting or restarting the audio sessions.
- Adds regression coverage for external auto-mute/restore and provider-switch route preservation.
- Corrects the bundled stable release-channel manifest to the published 0.25.7 asset/checksum, keeping update and rollback status grounded in the real current stable release.
- Continues the 0.25.7 proven topology: `skelly-ai` PipeWire owns external audio; `dadtech` PipeWire owns Skelly jaw audio; movement/control remains independent.

# UltraSkellyAdvanced 0.25.7

- Proven dual-session Bluetooth audio routing: Soundcore primary speech uses the `skelly-ai` PipeWire session while Animated Skelly(Live) jaw-mirror audio uses the `dadtech` PipeWire session.
- External Bluetooth, stock jaw audio, and Skelly movement/control can remain connected simultaneously across reboot.
- Renamed Audio/Jaw Sync to **Bluetooth Sync Compensation** and set the new-install default to **-750 ms**, based on real stock Skelly + Soundcore testing.
- External Bluetooth never silently falls back to the Skelly default sink when its PipeWire output is unavailable.
- Stale successful-update messages from older installed versions no longer remain pinned in the Updates card.

# 0.25.7.dev8 smoke-test changes

- Routes external Bluetooth speech through the `skelly-ai` PipeWire user session.
- Keeps Animated Skelly(Live) jaw-mirror audio in the `dadtech` PipeWire user session.
- Makes `audio-pw-play` and `audio-wpctl` session-aware with a strict `dadtech` / `skelly-ai` allowlist.
- Prevents External Bluetooth from falling back to an unrelated default sink when its PipeWire sink is unavailable.
- External-speaker readiness now checks the PipeWire session that actually owns the Soundcore.
- Preserves the proven three-link topology: Skelly control BLE + Skelly jaw/audio + external Bluetooth speaker.

# UltraSkellyAdvanced 0.25.7

## Highlights

- Adds Setup > Audio Output with **Skelly Speaker**, **External Bluetooth**, and **USB / Pi Audio** routing.
- External Bluetooth devices can be scanned, paired, remembered, forgotten, and automatically reconnected.
- Keeps the existing Skelly control/speaker pairing behavior separate from the new External Bluetooth route.
- Adds **Jaw follows speech** for stock/no-DAC Skelly by mirroring reply audio to Animated Skelly(Live) while the external speaker carries the main room audio.
- Adds **Jaw mirror level** (70–100%, default 100%) because real-hardware testing confirmed low mirror levels may not trigger the stock jaw.
- Replaces the one-way jaw delay with **Audio/Jaw Sync** from -1000 ms to +1000 ms in 25 ms steps. Negative values delay the external speaker; positive values delay the jaw mirror. The earlier dev default was -200 ms; 0.25.7 updates the reference default to -750 ms after full dual-session hardware testing.
- Uses the same signed dual-output timing for AI replies and Operator text-to-voice.
- External-speaker failures no longer block AI/Operator mode startup; reconnect runs in the background.
- Header status changes between **Skelly Speaker**, **External Speaker**, and **Pi / USB Audio** based on the active route.
- Hardens headless PipeWire/WirePlumber startup: the `dadtech` audio session now has linger enabled, a headless Bluetooth policy, boot-time user-manager ordering, and helper-driven recovery so cold boots do not leave audio at `Host is down`.
- PipeWire control/playback is intentionally executed in the persistent `dadtech` audio session while the main USA web service remains isolated as `skelly-ai`.

## Smoke-tested behavior

On the reference Pi, Soundcore Boom V2 and Animated Skelly(Live) coexist as separate PipeWire Bluetooth sinks. External speech plays through the Soundcore while mirrored Skelly audio drives the stock jaw. Earlier testing used -200 ms; full dual-session testing later established -750 ms as the reference compensation for the tested Soundcore + stock Skelly pair.

# 0.25.7.dev6 smoke-test changes

- Replaces one-way Jaw Sync Offset with **Audio/Jaw Sync** from -1000 ms to +1000 ms in 25 ms steps.
- Earlier dev default was -200 ms; 0.25.7 uses -750 ms based on the final tested dual-session topology.
- Negative values delay the external/main speaker while Skelly's jaw-mirror audio starts first.
- Positive values delay the Skelly jaw mirror.
- Applies the same signed timing behavior to file playback and streamed/operator TTS so Operator and AI use consistent dual-output sync.

## 0.25.7.dev5 — Shared audio session + reliable jaw mirror

- Routes PipeWire control/playback through the working `dadtech` user session while the main USA service remains isolated as `skelly-ai`.
- Fixes slow audio-status/mode transitions caused by the service looking at the wrong PipeWire session.
- External Bluetooth remains the main speech output while Animated Skelly(Live) receives a separate mirrored stream for stock jaw movement.
- Jaw mirror level defaults to 100% and is adjustable from 70–100%; testing showed lower levels can fail to trigger the stock jaw.
- Jaw sync offset now defaults to 0 ms.
- Keeps external-audio reconnect non-blocking so Operate/AI mode can start even if a speaker is unavailable.

## 0.25.7.dev4 — Non-blocking external audio startup

- Fixed Operate/AI startup failing when the selected External Bluetooth speaker is asleep, out of range, or times out.
- Skelly control, movement, and Live Mode now become ready independently of External Bluetooth availability.
- External Bluetooth reconnection remains a background task and reports a degraded/reconnecting state instead of returning a 503 for the operating mode.
- Retains dev3 headless WirePlumber support, exact PipeWire sink targeting, stock-jaw audio mirror, and dynamic speaker indicator.

## 0.25.7.dev3 — External audio routing smoke fix

- Adds the headless WirePlumber Bluetooth-seat configuration required for A2DP sinks on USA controllers.
- Uses PipeWire node names for explicit external-speaker and Skelly jaw-mirror playback targets.
- Keeps the Skelly sink at unity gain when it is used as the stock audio-reactive jaw mirror.
- Reconnects the Skelly jaw-audio path alongside the saved external Bluetooth speaker.
- Header speaker indicator now switches between Skelly Speaker, External Speaker, and Pi / USB Audio based on the selected route.
- Retains the dev2 scan/pair UI race fix and verifies Bluetooth connection state before reporting success.

# UltraSkellyAdvanced Release Notes

## 0.25.7.dev1 — External audio smoke test

- Adds Setup > Audio Output with **Skelly Speaker**, **External Bluetooth**, and **USB / Pi Audio** choices.
- Keeps the existing Skelly-speaker pairing/auto-connect path intact when Skelly Speaker is selected.
- Adds first-use discovery, pairing, saving, manual reconnect, forget, and background auto-reconnect for one External Bluetooth speaker.
- Adds **Jaw follows speech** and a 0–500 ms **Jaw sync offset** control.
- With DAC, jaw animation continues to follow the speech waveform in software regardless of speaker output.
- Without DAC, external/system speech can be mirrored to the connected Skelly speaker so its stock audio-reactive jaw can continue moving.
- If the Skelly jaw-audio path is unavailable, external/system speech is allowed to continue instead of blocking AI/Operator mode.

> Smoke-test note: stock/no-DAC jaw-follow depends on Skelly's onboard audio-reactive jaw receiving the mirrored speech audio. The real-hardware test should verify Bluetooth dual-output latency and whether the Skelly speaker level is acceptable alongside the external speaker.

## 0.25.6 Build 2 - Visitor engagement and Classic presets

## 0.25.6.dev5 — Multi-trigger AI + snapshot thumbnails

- Adds compact **Trigger on** checkboxes directly in Automatic AI Mode for Audio, Face, and Motion.
- Any enabled source can acquire a visitor; Audio wakes a new session immediately while Face/Motion retain visual confirmation behavior.
- Shows live activity dots for the three trigger sources.
- Replaces the event-log **View snapshot** text link with a clickable interaction thumbnail on desktop and mobile.
- Retains all 0.25.6.dev4 listening, lure, movement, and snapshot behavior.


- Active AI conversations keep listening through brief camera misses, so a stationary visitor does not have to move again just to reopen the listening window. Departure still requires the configured consecutive clear-frame confirmation.
- Added Visitor Engagement / Lure Mode: Disabled, Media, or AI, with first-nag delay, cooldown, max nags per visitor (1-5), and presence gating.
- Media Lure Mode reuses Classic Mode media files that are explicitly marked `Use as Lure response` and avoids repeating the same clip when alternatives exist.
- AI Lure Mode generates one short attention-getting line through the active AI/voice configuration.
- Classic preset movement is now an independent Head / Arm / Torso checkbox bitmask with an All convenience toggle, allowing every movement combination.
- Build 1 listening sensitivity, 90/50/30 response movement weighting, and reduced name repetition remain intact.

## 0.25.6 Build 1 - Interaction movement tuning

- AI response movement is now controller-weighted instead of model-selected: head 90%, torso 50%, arms 30% over time.
- Added the combined stock head+torso movement bitfield so the requested weighting can be achieved without overusing the noisy arms.
- Character prompting now avoids repeated self-introductions during an active conversation while still honoring the configured Skelly name when asked.
- Listening sensitivity tuning from the 0.25.6 listening test remains unchanged.
- Stock BLE still has no verified torso position/center command; responses continue to send a guaranteed Stop after speech rather than guessing at a recenter motion.

## 0.25.5 Stage 2 test checkpoint

- Adds ElevenLabs account voice-library selection with the selected Voice ID saved in provider settings.
- Caches the last successfully loaded ElevenLabs voice list on the Pi for later selection if the account endpoint is temporarily unavailable.
- Adds an ElevenLabs credits-remaining progress bar: green above 50%, yellow from 10% through 50%, red below 10%.
- Adds a Groq daily-requests-remaining progress bar using Groq rate-limit response headers.
- Makes Operator Console Laugh use the currently selected cloud voice when Groq or ElevenLabs is active, with stored/offline audio retained as fallback.
- Keeps manual ElevenLabs Voice ID entry under an Advanced-style expander for voices not returned by the account library.

# UltraSkellyAdvanced 0.25.4 Beta

### Stage 2B UI refinement
- Removed the Groq remaining-request meter from Voice Tuning.
- Kept the full ElevenLabs credits-remaining meter on Voice Tuning.
- Added a compact ElevenLabs fuel indicator to Operate when ElevenLabs is the selected voice provider.
- The Operate indicator uses the same green/yellow/red remaining-credit thresholds without duplicating the full Voice Tuning meter.

## 0.25.5 Stage 3 test checkpoint

- Adds one-click manual rollback to the previous known-good USA version from Diagnostics → USA updates.
- Rollback preserves owner settings, API credentials, WiFi configuration, media state, and other data under `/var/lib/skelly-ai`.
- Restored versions are health-checked before rollback is declared successful.
- If the restored version fails its health check, USA automatically returns to the newer working version.
- Rollback is offered only when retained backup metadata matches the currently running version.
- ElevenLabs permission guidance now reflects Stage 2 requirements: Text to Speech Access, Voices Read, Models Access, and User Access for the credit balance.

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

### Lure Visitors and interaction snapshots
- Renames visitor attention controls to **Lure Visitors** throughout the UI.
- Saves one local JPEG snapshot for each accepted visitor interaction/AI response.
- Interaction event logs provide a **View snapshot** link when capture succeeds.
- Keeps only the latest 100 interaction snapshots to cap storage use.
