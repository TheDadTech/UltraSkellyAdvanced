# Public distribution workflow

## Recommended hosting

Use a GitHub Release as the versioned source of truth for the image, checksum,
build information, source archive, and release notes. Use lightshow.tech as the
friendly landing page and link its download button to that GitHub Release.
This prevents a website redesign from breaking old versioned downloads.

## Files for each release

- `UltraSkellyAdvanced-VERSION.img.xz` (the pi-gen filename may include a date prefix)
- matching `.sha256`
- matching `.build-info.txt`
- `UltraSkellyAdvanced-VERSION-beta.zip`
- `QUICK_START.md`
- `RELEASE_NOTES.md`
- `NOTICE.md`

Do not publish development SD-card clones, `/var/lib/skelly-ai`, API keys,
Bluetooth bonds, logs, packet captures, `.env` files, or router-specific data.

## Release steps

1. Run the automated test suite and the image release gate.
2. Build on Ubuntu with `./image/build-image.sh --docker`.
3. Verify the checksum before flashing the test card.
4. Complete a clean first boot on a separate card with no peripherals attached.
5. Test Standard hardware, then Advanced hardware, using throwaway provider keys.
6. Upload the seven release files to a GitHub prerelease marked **Beta**.
7. Point the lightshow.tech download page to the GitHub Release.
8. Keep the previous known-good image available for rollback.

## Update manifest

After the final release-package URL exists, publish an HTTPS JSON file following
`docs/latest-manifest.example.json`. `package_url` must point directly to the USA
release ZIP and `sha256` must be that ZIP's lowercase SHA-256 digest. The
dashboard will offer **Install update** only when both fields are present. It
downloads the ZIP, verifies the checksum, validates the packaged version, and
keeps the previous application environment for automatic rollback if the new
service fails its health check.

## Licensing decision before a public source repository

Choose and add a software license before making the source repository public.
No license means outside contributors do not automatically receive permission
to copy, modify, or redistribute the source. The SD image can remain an Early
Access binary download while that owner decision is pending.
