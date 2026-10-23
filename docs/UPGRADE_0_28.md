# USA 0.28.0 local candidate: upgrade, backup and recovery

This checkout is a local candidate. A successful Ubuntu test run or image build
is not a Pi hardware qualification. Do not publish as stable until the image
release gate has passed on a disposable SD card.

## Backup and restore

In **System & Tools → Backup / Restore**, choose a password of 12–256 characters.
Download Backup creates a versioned encrypted `.usabackup` file. It uses scrypt
(N=32768, r=8, p=1) and AES-256-GCM with fresh random salt and nonce. Losing the
password makes the backup unrecoverable. Keep the password separately.

Backups include persisted installation/device preferences, voice/provider
settings, saved Groq and ElevenLabs credentials, Pi Media metadata (including
stable IDs and lure eligibility), and stock lure assignments. Effective API
credentials and settings supplied by environment defaults are captured too.
Select **Include Pi Media audio files** to include audio; Check backup size shows
the uncompressed size. The encrypted upload and expanded contents are limited
to 128 MiB. For larger libraries, copy audio separately and make a settings-only
backup. Metadata remains dormant until matching filenames are copied back.

Excluded: OS WiFi passwords, BlueZ bonds, host environment files, TTS access
password, FPP token, update-channel opt-in, temporary previews, local models,
logs, and update staging. Reconfigure host-specific settings and pair speakers
on a replacement controller. Restoring does not silently enable beta updates.

Select a backup, enter its password, and choose Preview Restore. Review the
filenames and size before confirming Restore Backup. Stop the running operation
first. The server validates the full archive before replacing allowlisted files,
rejects symlinks and path traversal, and preserves an encrypted settings recovery
copy using the same password. Different existing audio files are never silently
overwritten. Recovery copies can be listed and downloaded in the GUI. Restart
USA after restoring; do not operate the prop until settings have been reviewed.
The restore operation is process-local; run a single application worker. A power
loss during replacement of multiple files is not transactional; the recovery
copy remains available. Do not restore during other file transfers.

## Protected tools

TTS, backups, and manual ZIP tools share the existing operator Basic credentials:
`SKELLY_TTS_USERNAME` (default `operator`) and `SKELLY_TTS_PASSWORD` (12+ characters).
Without credentials configured, these routes accept only direct loopback access.
Proxy/LAN access requires credentials. Existing ordinary control/setup routes
retain their previous access policy. Use HTTPS for network access.

Use **System & Tools → Sign in to protected tools**. Credentials remain in tab
memory and are cleared by reload; they are never stored in localStorage. The
GUI loads protected audio into an in-memory browser preview. This flow works
without relying on a native browser Basic-auth dialog. The backup password is
separate from the operator login and is never saved by USA.

## Normal and manual updates

Use Check for updates to see installed and latest detected versions, reachability,
and last successful check. Stable is the default. Beta remains explicit opt-in;
beta checks also fetch stable metadata. Connectivity checks do not install or
contact voice providers. Failed checks retain the last known successful versions.

For a manual update, download the official USA release ZIP and its SHA-256 from
the project's release page. Upload the ZIP, enter its version and published
checksum, and choose Upload and verify ZIP. Do not use a checksum supplied by an
untrusted third party. The checksum verifies integrity, not a digital signature.
ZIPs are limited to 150 MiB, expanded contents to 350 MiB, and 5,000 entries;
unsafe paths, duplicate entries, symlinks and incomplete packages are rejected.

Verification does not install. Stop the current operation and explicitly confirm
Install verified ZIP. Verification expires after 30 minutes or an app restart.
The server rechecks bytes and extracts again before invoking the existing system
helper in its existing versioned staging directory. Simulation refuses installation.
The existing installer health checks and automatic rollback remain authoritative.
Manual upload refuses same/older versions; use Roll back for a previous release.
Beta packages require Beta opt-in. A user-entered digest does not make arbitrary
third-party code trustworthy: install only the owner's intended official release.

## Older 0.27.x installations

A 0.27.x dashboard cannot gain the new upload controls until it is upgraded. Try
its normal updater first. Compatibility of config defaults, filename-based media
operations, update and rollback behavior is covered by local tests; actual
0.27.4 → 0.28.0 installation remains a disposable-card release gate.

If its updater is broken, an owner can use the supplied one-time recovery script
with a downloaded official ZIP and independently obtained checksum:

```bash
sudo bash scripts/install-updater-bridge.sh VERSION /absolute/path/to/release.zip PUBLISHED_SHA256
```

This replaces the obsolete hard-coded 0.25.6 bridge. It validates version and
checksum, refuses same/older base versions, validates ZIP contents, preserves a
unique backup of the previous environment/system files, and uses the existing
bootstrap installer and health check. It preserves application data. It needs
one supervised terminal command on the controller; no script has been run on
production during Ubuntu development. Never run the historical 0.25.6 bridge to
repair a newer installation. This path needs isolated Pi testing before release.

## System Health and The Lab

System Health reports storage, media quota, application/control/audio status,
offline speech availability, cloud configuration without keys, release-service
status and suggested next steps. Read-only host probes cover Bluetooth,
PipeWire, camera, microphones, network, USA and nginx services. Raw details are
under Advanced diagnostic details. Simulation labels host probes as not probed;
it does not qualify real hardware.

The Lab separates sensor tests and advanced DAC experiments from normal use.
Existing hardware/profile safety guards remain in effect. Sensor actions and
movement experiments must be deliberately requested; clear the prop first.

## Build and release gates

Run `bash scripts/test-dev.sh -q`, JavaScript syntax checks, dependency checks,
nginx config validation and `image/release-preflight.sh`. Build the local release
ZIP with `scripts/package-release.sh ROOT NEW_OUTPUT_DIRECTORY`; existing ZIPs
and checksums are never overwritten. Build the arm64 image on Ubuntu with
`image/build-image.sh --docker` and a fresh `SKELLY_IMAGE_BUILD_DIR`.

Do not publish or deploy until `docs/IMAGE_RELEASE_GATE.md` passes, including
fresh boot, old-version upgrade/rollback, Bluetooth routing, jaw/movement,
cold reboot, credential restore, and selected real cloud-provider checks.
