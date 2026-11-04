# FPP synchronized singing

This is an unpublished 0.29.0-beta1 candidate. Both features are opt-in under Setup → Optional integrations. Do not confuse local unit/simulation checks with physical jaw or audio verification.

## FPP

Enable synchronized singing, enter the Main FPP player's IPv4 address and save. FPP's built-in MultiSync multicast must be enabled, and Main and USA must have multicast-capable LAN connectivity. No FPP code/plugin modifications are needed. USA joins 239.70.80.80 UDP32320 and accepts media timing only from that source IP. UDP has no authentication; keep the show network trusted. No remotely supplied commands/plugins are executed.

Upload the a cappella track through The Lab to Pi Media with exactly the media filename sent by Main, including extension/case. USA never downloads a song from Main and will play nothing without a matching local file. Currently IPv4 is supported; hostname discovery and general audio aliases are not implemented; the sequence importer below has an explicit song-to-generated-WAV link.

The connection badge reflects HTTP reachability of FPP; it is independent of whether a song is playing. Operate shows Now playing when a matching local song is active. The background timeline advances during higher-priority USA speech/media. The existing Jaw / Audio timing adjustment also applies: jaw-sooner seeks ahead in the local track; jaw-later seeks behind, clamped at the start. Real Bluetooth/jaw timing still needs physical calibration. The background player is canceled, cleaned up, and restarted at the current position after foreground output finishes. Loss of sync for more than five seconds stops eligibility; playback errors do not retry continuously.

Stock FPP singing now requires audible playback: physical testing showed that onboard-volume muting held the jaw open. The settings API and playback supervisor reject silent stock operation, including legacy settings. Advanced motor hardware is parked outside the current user workflow. Audible phoneme pulse singing was physically reported successful by the User on one stock Skelly, not validated across hardware revisions. This candidate does not provide user-adjustable source priorities.

### FSEQ singing importer (development candidate)
Setup → FPP singing integration → Sequence singing supports local FSEQ upload or read-only download from the configured Main FPP. Requires FSEQ v2 embedded xLights XS data and a system libzstd library. Lists only timing layers with recognized phonemes. Named tracks can be chosen independently for different singers; the whole chosen track is used (model effect windows and lead settings are not automatically applied yet). Negative timing adjustment advances pulses; positive delays them. Audio filename is prefilled from FSEQ media metadata and can be corrected to the actual FPP audio filename.

Preparation generates a registered WAV in Pi Media, retaining original audio. A persistent explicit song-to-generated-file map avoids renaming uploaded audio. “Use matching audio instead” removes the sequence link. Stop FPP before changing parts. Uses calibrated trial200Hz pulses with caps AI/O100ms,E/U/L75ms,FV/WQ/etc50ms,35% minimum release,6500/32768 peak and2ms ramps. The original -750ms USA jaw/audio setting remains independent of the new per-track offset. Max FSEQ512MB, embedded XML24MB, song30min. Files lacking embedded phonemes fail with a clear error. No FPP configuration, sequence, plugin, or playback changes are made by importing.

Audible stock pulse singing has been physically reported successful by the User. Silent onboard-volume muting has NOT passed physical verification and remains under investigation. The overnight image predates this importer and does not include these changes.


Release audit hardening: parsing and generation run in disposable subprocesses (512 MiB address-space,40 CPU seconds,60 wall seconds,100 MiB output cap). Cancellation kills and reaps the child before deleting files or releasing the import lock. Imports have120-second wall limit; busy imports return409 rather than queue. Metadata cache retains at most31 recent imports (24-hour age pruning); generated tracks use deterministic content identities to reuse identical preparations. Pi Media quota/free-space checks apply, and failed link commits remove newly generated assets while preserving the prior link. Exact duplicate phonemes are removed; overlaps no larger than one sequence frame are clipped at the next cue, with an adjustment count. Larger/ambiguous overlaps are rejected. Original audio is never renamed or overwritten.


FPP Override is one saved setting shared by the AI trigger strip and FPP song library. Enabled: a fresh matching song cancels AI listening/responses and lures, clears that interaction, and resumes monitoring after output cleanup when the song stops, becomes stale, or has no matching local asset. A deliberate User Stop is preserved and is never undone by song end. Manual operator speech remains foreground. Disabled: FPP stays a background source and interactions take priority as before.

Generated tracks have friendly song/part names, a collapsed library group, and Preview Jaw Movement / Edit / Delete. The usual eyes/lights/body movement preset is available; new generated assets default to no body movement. A per-track jaw timing slider replaces the generic jaw-sync checkbox and does not alter other songs. Switching to a recording requires choosing an existing enabled audio file, preserves the generated asset and its identity, and allows switching back.
