> Scope correction: the release scope below was superseded by `SCOPE_0_28.md`.
> It records the earlier broader handoff audit, not additional release commitments.

# 0.28.0 plan audit — 2026-10-22 Ubuntu

Audit baseline: `dev/0.28.0`, HEAD `16b0379`, plus three preserved uncommitted
changes (nginx Host port and eye/Lure regression tests). No reset or discard.
The full owner recovery handoff was read during this audit.

| Original item | At audit start | Current local implementation | Verification / remaining gate |
| --- | --- | --- | --- |
| Pi Media overhaul | Implemented | Streaming/progress/cancel, quotas, friendly names, permanent IDs, migration, lure-first table, compact eye picker; synchronous overwrite race fixed | Automated/API + Ubuntu browser verified; physical playback pending |
| TTS hardening | Implemented | Existing preview auth, quotas, expiry, locks, no prop playback during generation; GUI operator sign-in added | Automated/API and real local browser generation/playback/save/discard; authenticated nginx browser preview/discard verified; live cloud services pending |
| Backup/Restore | Absent | Versioned AES-GCM/scrypt encrypted credentials/settings/media backups, preview, allowlist/size validation, recovery copies and download | Round-trip/tamper/password/path/symlink/collision tests; Ubuntu browser download/inspect/restore verified; replacement-Pi recovery pending |
| Manual ZIP update | Absent; online updater existed | Bounded upload, published digest/version/package validation, beta/downgrade guards, expiry, explicit helper installation, simulation guard | Tests recheck bytes and helper staging; Ubuntu authenticated browser upload/verify; real install/rollback pending |
| GitHub status | Basic check only | Installed/latest detected versions, reachable/unreachable, cached success/error/time; stable and opted-in beta | Success/failure/persistence tests; no publication performed |
| Older-version recovery | Bridge pinned to obsolete 0.25.6 | Explicit local release/version/checksum bridge, no silent downgrade, unique backups and existing bootstrap/health checks | Standalone archive validator tested; 0.27.4/other 0.27.x installation unverified on hardware |
| System Health | Raw diagnostics | Readable status, storage/media/provider/dependency summaries, remedies, host service/device probes; advanced details preserved | API/simulation/browser verified; real host signals and hardware remedies pending |
| The Lab | No separate tab | Separate experimental/sensor/DAC tab and cautions; existing profile/mode guards retained | Navigation/browser + static tests; no physical experiments run |
| Version and release notes | Metadata 0.27.6; notes older | Metadata/cache version 0.28.0, candidate notes and upgrade guide | Local checks; release gate still required |
| Release ZIP | Existing builder | Local candidate ZIP/checksum; refuses overwriting artifacts and excludes caches/backups | Artifact inspection and checksum required after build |
| Pi image | Existing Ubuntu pi-gen builder | Uses clean source whitelist; source/cache exclusions tightened; fresh build workspace | Build result recorded in task output; boot/hardware qualification never implied |
| Final hardware smoke test | Not done | Intentionally not run | Owner authorization and disposable SD card required |

## Existing UX checked in source

`choose_ai_response_movement()` already implements the requested marginal rates
(head 90%, torso 50%, arm 30%). The current app also retains adjustable listening
sensitivity, phantom-transcript filters, camera/audio/motion triggers, visitor
lures, saved speaker preferences, and safe show-mode restrictions. This audit
does not qualify their physical timing or Bluetooth behavior.

Stable media IDs survive restore and metadata-only restoration. Dedicated FPP
playback by ID remains a **long-term integration item** from the handoff; current
filename-based operations remain compatible. No new FPP hardware commands were
added as part of this release-critical maintenance work.

## Limits and open qualification

- Backups max 128 MiB; larger audio libraries need separate file copying.
- Backups exclude OS WiFi/BlueZ state, environment files and access/FPP tokens.
- Restores require idle operation and a restart; multi-file replacement is not
  power-loss atomic, with an encrypted recovery copy retained.
- Maintenance/preview locks are process-local: run one worker.
- Manual ZIP provenance depends on the owner using the official published digest;
  there is no newly introduced digital signing infrastructure.
- GUI sign-in works without a native Basic prompt; the embedded browser's native
  prompt itself was not validated.
- Real cloud billing calls, audio routing, stock jaw, movement, Bluetooth,
  clean/cold boot, old-install upgrade and rollback remain release gates.
- No Pi connection, push, publication or deployment was authorized or performed.
