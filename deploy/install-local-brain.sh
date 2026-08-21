#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run this script as the normal Pi user; it will use sudo when required." >&2
  exit 1
fi

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "This installer currently supports the 64-bit Raspberry Pi image (aarch64)." >&2
  exit 1
fi

LLAMA_RELEASE="b9637"
LLAMA_ARCHIVE="llama-${LLAMA_RELEASE}-bin-ubuntu-arm64.tar.gz"
LLAMA_SHA256="211d9e9ee738698beb7ca271be82661ae2b5da3fbb489cf7d9e4e6ed601be106"
LLAMA_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_RELEASE}/${LLAMA_ARCHIVE}"
LLAMA_DIR="/opt/skelly-ai/llama-${LLAMA_RELEASE}"

MODEL_NAME="qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_SHA256="6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/${MODEL_NAME}"
MODEL_DIR="/var/lib/skelly-ai/models"
MODEL_PATH="${MODEL_DIR}/${MODEL_NAME}"

SKELLY_USER="$(id -un)"
SKELLY_GROUP="$(id -gn)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf -- "${TEMP_DIR}"' EXIT

sudo apt-get update
sudo apt-get install -y ca-certificates curl

echo "Downloading the pinned llama.cpp ARM64 runtime (about 12 MB)..."
curl --fail --location --retry 5 --output "${TEMP_DIR}/${LLAMA_ARCHIVE}" "${LLAMA_URL}"
echo "${LLAMA_SHA256}  ${TEMP_DIR}/${LLAMA_ARCHIVE}" | sha256sum --check --status || {
  echo "llama.cpp checksum verification failed; nothing was installed." >&2
  exit 1
}

sudo install -d -m 0755 "${LLAMA_DIR}"
sudo tar -xzf "${TEMP_DIR}/${LLAMA_ARCHIVE}" -C "${LLAMA_DIR}"
SERVER_PATH="$(find "${LLAMA_DIR}" -type f -name llama-server -print -quit)"
if [[ -z "${SERVER_PATH}" ]]; then
  echo "The verified archive did not contain llama-server." >&2
  exit 1
fi
SERVER_DIR="$(dirname "${SERVER_PATH}")"

sudo install -d -m 0755 -o "${SKELLY_USER}" -g "${SKELLY_GROUP}" "${MODEL_DIR}"
if [[ -f "${MODEL_PATH}" ]] && echo "${MODEL_SHA256}  ${MODEL_PATH}" | sha256sum --check --status; then
  echo "The verified Qwen model is already installed."
else
  echo "Downloading Qwen 2.5 1.5B Q4_K_M (about 1.12 GB)..."
  curl --fail --location --retry 5 --continue-at - \
    --output "${MODEL_PATH}.part" "${MODEL_URL}"
  echo "${MODEL_SHA256}  ${MODEL_PATH}.part" | sha256sum --check --status || {
    echo "Model checksum verification failed; the partial file was retained for inspection." >&2
    exit 1
  }
  mv "${MODEL_PATH}.part" "${MODEL_PATH}"
fi

sudo tee /etc/systemd/system/skelly-brain.service >/dev/null <<EOF
[Unit]
Description=Skelly AI local Qwen brain
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SKELLY_USER}
Group=${SKELLY_GROUP}
Environment=LD_LIBRARY_PATH=${SERVER_DIR}
ExecStart=${SERVER_PATH} --model ${MODEL_PATH} --alias skelly-local --host 127.0.0.1 --port 8790 --ctx-size 2048 --threads 4 --parallel 1
Restart=on-failure
RestartSec=5
Nice=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now skelly-brain

echo "Waiting for the model to load..."
for _ in $(seq 1 60); do
  if curl --silent --fail http://127.0.0.1:8790/health >/dev/null; then
    echo "Local Qwen brain is ready."
    echo "Status: systemctl status skelly-brain"
    exit 0
  fi
  sleep 3
done

echo "The service was installed but did not become ready within three minutes." >&2
echo "Check: sudo journalctl -u skelly-brain -n 80 --no-pager" >&2
exit 1
