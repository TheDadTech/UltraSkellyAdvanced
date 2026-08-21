#!/usr/bin/env bash
set -euo pipefail

# Build a clean UltraSkellyAdvanced Raspberry Pi OS image from source. This intentionally
# never reads a mounted development SD card or /var/lib/skelly-ai.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${SKELLY_IMAGE_BUILD_DIR:-${PROJECT_DIR}/.image-build}"
PI_GEN_DIR="${BUILD_DIR}/pi-gen"
CUSTOM_STAGE="${PI_GEN_DIR}/stage-skelly-ai"
CONFIG_FILE="${PI_GEN_DIR}/config"
BUILD_MODE="${1:---docker}"
SKELLY_VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${PROJECT_DIR}/pyproject.toml" | head -n 1)"

if [[ -z "${SKELLY_VERSION}" ]]; then
    echo "Unable to read the USA version from pyproject.toml." >&2
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "The SD image builder must run on Linux (the Ubuntu laptop is suitable)." >&2
  exit 1
fi

for command in git tar sha256sum; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

mkdir -p "${BUILD_DIR}"
if [[ ! -d "${PI_GEN_DIR}/.git" ]]; then
  git clone --depth 1 --branch arm64 \
    https://github.com/RPi-Distro/pi-gen.git "${PI_GEN_DIR}"
fi

# Some Docker hosts report an unused loop device as "/dev/loopN (lost)".
# pi-gen's current parser treats that entire string as the minor number and
# fails during final image export. Keep only the device path before pi-gen
# creates the missing block-device node.
PI_GEN_COMMON="${PI_GEN_DIR}/scripts/common"
if grep -Fq 'loopdev="$(losetup -f)"' "${PI_GEN_COMMON}"; then
  sed -i \
    's@loopdev="$(losetup -f)"@loopdev="$(losetup -f | cut -d" " -f1)"@' \
    "${PI_GEN_COMMON}"
  sed -i \
    's@^[[:space:]]*loopmaj=.*@\tloopmaj="${loopdev##*/loop}"@' \
    "${PI_GEN_COMMON}"
fi

# pi-gen's default export margin (20% plus 200 MiB) is too small while the
# Skelly AI image performs its final package-index refresh. Reserve 3 GiB;
# unused space compresses efficiently in the distributed .img.xz file.
PI_GEN_EXPORT_PRERUN="${PI_GEN_DIR}/export-image/prerun.sh"
sed -i \
  's@^ROOT_MARGIN=.*@ROOT_MARGIN="$((3 * 1024 * 1024 * 1024))"@' \
  "${PI_GEN_EXPORT_PRERUN}"

rm -rf "${CUSTOM_STAGE}"
cp -a "${SCRIPT_DIR}/pi-gen-stage" "${CUSTOM_STAGE}"
mkdir -p "${CUSTOM_STAGE}/00-install-skelly-ai/files"

# A whitelist prevents local credentials, pairings, caches, release ZIPs, and
# development state from ever entering the image build context.
tar -C "${PROJECT_DIR}" -czf \
  "${CUSTOM_STAGE}/00-install-skelly-ai/files/skelly-ai-source.tar.gz" \
  --exclude='src/*.egg-info' \
  pyproject.toml README.md src deploy

cat >"${CONFIG_FILE}" <<EOF
IMG_NAME='UltraSkellyAdvanced-${SKELLY_VERSION}'
PI_GEN_RELEASE='UltraSkellyAdvanced ${SKELLY_VERSION} Beta'
RELEASE='trixie'
DEPLOY_COMPRESSION='xz'
TARGET_HOSTNAME='usa-controller'
ENABLE_CLOUD_INIT=1
FIRST_USER_NAME='dadtech'
FIRST_USER_PASS='dadtech'
DISABLE_FIRST_BOOT_USER_RENAME=1
PASSWORDLESS_SUDO=0
LOCALE_DEFAULT='en_US.UTF-8'
KEYBOARD_KEYMAP='us'
KEYBOARD_LAYOUT='English (US)'
TIMEZONE_DEFAULT='America/New_York'
STAGE_LIST='stage0 stage1 stage2 stage-skelly-ai'
EOF

chmod +x \
  "${CUSTOM_STAGE}/prerun.sh" \
  "${CUSTOM_STAGE}/00-install-skelly-ai/00-run.sh" \
  "${CUSTOM_STAGE}/00-install-skelly-ai/files/install-chroot.sh"

pushd "${PI_GEN_DIR}" >/dev/null
case "${BUILD_MODE}" in
  --docker)
    ./build-docker.sh
    ;;
  --native)
    if [[ "${EUID}" -ne 0 ]]; then
      echo "Native image builds must run as root. Use sudo or --docker." >&2
      exit 1
    fi
    ./build.sh
    ;;
  *)
    echo "Usage: $0 [--docker|--native]" >&2
    exit 1
    ;;
esac
popd >/dev/null

mapfile -t images < <(find "${PI_GEN_DIR}/deploy" -maxdepth 1 -type f \
  \( -name "*UltraSkellyAdvanced-${SKELLY_VERSION}*.img.xz" -o -name "*UltraSkellyAdvanced-${SKELLY_VERSION}*.zip" \) -print)
if [[ "${#images[@]}" -eq 0 ]]; then
  echo "Build completed, but no compressed USA image was found." >&2
  exit 1
fi

for image in "${images[@]}"; do
  image_dir="$(dirname "${image}")"
  image_name="$(basename "${image}")"
  (
    cd "${image_dir}"
    sha256sum "${image_name}" >"${image_name}.sha256"
  )
  cat >"${image}.build-info.txt" <<EOF
USA version: ${SKELLY_VERSION}
Release channel: Beta
Raspberry Pi OS: trixie arm64
pi-gen commit: $(git -C "${PI_GEN_DIR}" rev-parse HEAD)
Built UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source SHA-256: $(sha256sum "${CUSTOM_STAGE}/00-install-skelly-ai/files/skelly-ai-source.tar.gz" | awk '{print $1}')
EOF
  echo "Image: ${image}"
  echo "Checksum: ${image}.sha256"
  echo "Build information: ${image}.build-info.txt"
done
