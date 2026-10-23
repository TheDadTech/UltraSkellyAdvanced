# 0.28.0 corrected release audit

The owner's scope correction supersedes the broader recovery handoff. No new
experimental or health workstream is part of this release.

| Requirement | Audit finding | Corrected local state |
| --- | --- | --- |
| 1. Classic → The Lab | Classic media remained in Operate; Lab was separate experiments | The Lab replaces the Classic mode card under Operate; selecting it shows Classic media. Help Mode is first in System & Tools, followed by Camera & Microphone. There is no separate Lab tab; existing DAC tools stay under System & Tools |
| 2. Pi Media | Lure column, friendly names and graphical eyes already implemented | Preserved: first-column Lure, none in Edit, editable Media Name, 18 graphical eyes in 3×6 with 26px images, hover/accessibility/selection; internal filename removed from table subtitle and Pi editor heading |
| 3. Create TTS Media | Implemented and browser/API tested | Existing providers, cached preview, discard and save preserved; access sign-in appears only when required |
| 4. Uploads | Streaming, nginx limits and improved errors implemented | Preserved; exclusive publication avoids silent collision overwrite |
| 5. Welcome Message | Still exposed and active | GUI and automatic greeting hook removed; dormant legacy fields retained without resetting unrelated settings |
| 6. Backup & Restore | Encrypted backup implemented during this audit | Settings/credentials encryption, validation, restore preview and recovery preserved |
| 7. Manual GitHub ZIP update | Implemented with existing helper/rollback | Upload validation shows target version and uses local bytes/checksum; no controller password is required; verification/install does not fetch a GitHub manifest; simulation refuses installation |
| 8. Compact System & Tools | Working functions filled a long page | Help Mode first, then Camera & Microphone; expandable dark cards preserve other tools. No standalone sign-in section |
| 9. Dark visual identity | Existing dark palette | Retained; no theme replacement |

Full automated and focused browser smoke results are recorded in the task's
verification output. Camera/microphone interactivity is tested with injected
fixtures rather than operating physical hardware. Real Pi boot, audio routing,
jaw, movement, Bluetooth and upgrade/rollback still require authorized isolated
hardware testing. Live cloud-credit calls have not been made. Existing System
Health and connectivity reporting remain; neither is expanded further.

Image builds use a fresh versioned Ubuntu workspace, leave earlier artifacts
intact, and do not push, publish, flash or install on production hardware.
