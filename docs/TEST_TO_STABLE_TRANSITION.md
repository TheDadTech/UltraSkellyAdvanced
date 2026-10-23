# 0.28.x test builds to 0.28.0 stable

The public stable release for this development cycle remains **0.28.0**.
Numeric 0.28.1 and 0.28.2 were interim Beta/test installations, not stable patches.

The existing **Return to Stable** action is reused. Build identity is separate
from the selected update feed: selecting Stable does not turn a Beta build into
a stable installation. Current development metadata marks the build as Beta and
explicitly names 0.28.0 as its planned stable transition target.

## Restrictions

- Stop active operation first. Same-origin and maintenance guards apply.
- Read the hard-coded official stable manifest, ignoring custom/Beta feed URLs.
- For this development cycle, proceed only when that manifest declares stable
  0.28.0 and points to the exact official GitHub 0.28.0 ZIP asset.
- The existing checksum, archive structure/version checks and installer are used.
- Ordinary update/manual-upload downgrade guards remain unchanged.
- Until official stable 0.28.0 exists, reject the transition without installation.
- If staging or installer startup fails, restore the previously selected feed.
- Pass the actual installed test version to the existing installer as the
  rollback predecessor. Version ordering does not prevent rollback to that saved
  test installation after stable is installed.

## Delivery prerequisite

Previously installed 0.28.1/0.28.2 binaries do not gain this behavior remotely.
First install a newer transition-aware test candidate through their existing
updater/manual upload. Such a delivery candidate (for example 0.28.3-beta1) must
retain both explicit build metadata fields. Then use Return to Stable once the
approved official 0.28.0 stable package is published.

This document does not authorize publishing that candidate or installing it on
production. Those remain separate owner-approved actions.

## Final stable packaging

Set all application/package versions to 0.28.0, set `__release_channel__` to
`"stable"`, and set `__stable_transition_target__` to `None`. Refresh frontend
asset versions. Stable installations must not advertise Return to Stable.
Do not reuse a previous numeric test artifact as the final stable package.

Local tests exercise real package hashing/extraction with mocked HTTPS downloads
and a mocked privileged installer. They verify rollback handoff, channel/settings
retention, bad checksums/versions, source restrictions, idle/origin guards and
unchanged ordinary downgrade rejection. They do not qualify a physical rollback
or service restart on a Pi.
