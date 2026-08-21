#!/usr/bin/env bash
set -euo pipefail

MODEL_NAME="vosk-model-small-en-us-0.15"
MODEL_ROOT="${SKELLY_MODEL_ROOT:-/var/lib/skelly-ai/models}"
MODEL_PATH="${MODEL_ROOT}/${MODEL_NAME}"
MODEL_URL="https://alphacephei.com/vosk/models/${MODEL_NAME}.zip"
MODEL_SHA256="30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498"

if [[ -d "${MODEL_PATH}" ]]; then
  echo "Offline speech model is already installed at ${MODEL_PATH}"
  exit 0
fi

if ! command -v curl >/dev/null || ! command -v unzip >/dev/null; then
  echo "Install curl and unzip first: sudo apt-get install -y curl unzip" >&2
  exit 1
fi

install -d -m 0755 "${MODEL_ROOT}"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT
ARCHIVE="${TEMP_DIR}/${MODEL_NAME}.zip"

echo "Downloading the 40 MB offline English speech model..."
curl --fail --location --progress-bar "${MODEL_URL}" --output "${ARCHIVE}"
echo "${MODEL_SHA256}  ${ARCHIVE}" | sha256sum --check --status

unzip -q "${ARCHIVE}" -d "${TEMP_DIR}"
mv "${TEMP_DIR}/${MODEL_NAME}" "${MODEL_PATH}"
chmod -R u+rwX,go+rX "${MODEL_PATH}"

echo "Offline speech model installed at ${MODEL_PATH}"
