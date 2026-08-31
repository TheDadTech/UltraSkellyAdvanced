#!/usr/bin/env bash
set -Eeuo pipefail

TARGET_VERSION="0.25.6"
RELEASE_URL="https://github.com/TheDadTech/UltraSkellyAdvanced/releases/download/v${TARGET_VERSION}/UltraSkellyAdvanced-${TARGET_VERSION}-beta.zip"
EXPECTED_SHA256="d7f8ce477a0d7df4d8646a3925fdfb56848033bbd797b0e24341d354061ed590"
DATA_DIR="/var/lib/skelly-ai"
WORK_DIR="${DATA_DIR}/bridge-work"
BACKUP_DIR="${DATA_DIR}/bridge-backup"
ACTIVE_VENV="/opt/skelly-ai/venv"
BACKUP_VENV="/opt/skelly-ai/venv.pre-updater-bridge"

log() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

if [[ ${EUID} -ne 0 ]]; then
  fail "Run this bridge as root, for example: curl -fsSL <bridge-url> | sudo bash"
fi

command -v curl >/dev/null 2>&1 || fail "curl is required."
command -v python3 >/dev/null 2>&1 || fail "python3 is required."
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required."

INSTALLING_USER="${SUDO_USER:-}"
if systemctl cat skelly-ai.service >/dev/null 2>&1; then
  SERVICE_USER="$(systemctl show skelly-ai.service -p User --value 2>/dev/null || true)"
  if [[ -n "${SERVICE_USER}" ]]; then
    INSTALLING_USER="${SERVICE_USER}"
  fi
fi
if [[ -z "${INSTALLING_USER}" || "${INSTALLING_USER}" == "root" ]]; then
  if id dadtech >/dev/null 2>&1; then
    INSTALLING_USER="dadtech"
  else
    INSTALLING_USER="pi"
  fi
fi

mkdir -p "${DATA_DIR}"
chmod 700 "${DATA_DIR}" || true
rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}/source" "${BACKUP_DIR}"

restore_legacy() {
  set +e
  printf '\nBridge installation failed. Attempting to restore the previous USA install...\n' >&2
  systemctl stop skelly-ai.service >/dev/null 2>&1 || true

  if [[ -d "${BACKUP_VENV}" ]]; then
    rm -rf "${ACTIVE_VENV}"
    mv "${BACKUP_VENV}" "${ACTIVE_VENV}"
  fi

  local paths=(
    "/usr/local/libexec/usa-system-helper"
    "/etc/systemd/system/skelly-ai.service"
    "/etc/systemd/system/usa-network.service"
    "/etc/nginx/sites-available/usa"
    "/etc/skelly-ai/skelly-ai.env"
  )
  local path backup
  for path in "${paths[@]}"; do
    backup="${BACKUP_DIR}${path}"
    if [[ -f "${backup}" ]]; then
      mkdir -p "$(dirname "${path}")"
      cp -a "${backup}" "${path}"
    fi
  done

  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl restart nginx.service >/dev/null 2>&1 || true
  systemctl restart skelly-ai.service >/dev/null 2>&1 || true
  printf 'Previous USA files restored where possible.\n' >&2
}
trap 'rc=$?; if [[ $rc -ne 0 ]]; then restore_legacy; fi; exit $rc' EXIT

log "Preparing one-time updater bridge to USA ${TARGET_VERSION}"

# Keep owner settings outside /opt untouched. Back up the legacy app environment
# and the small set of privileged/system files that the updater-enabled release replaces.
rm -rf "${BACKUP_DIR}"
mkdir -p "${BACKUP_DIR}"
if [[ -d "${ACTIVE_VENV}" ]]; then
  log "Backing up current USA Python environment"
  rm -rf "${BACKUP_VENV}"
  cp -a "${ACTIVE_VENV}" "${BACKUP_VENV}"
fi

for path in \
  /usr/local/libexec/usa-system-helper \
  /etc/systemd/system/skelly-ai.service \
  /etc/systemd/system/usa-network.service \
  /etc/nginx/sites-available/usa \
  /etc/skelly-ai/skelly-ai.env; do
  if [[ -f "${path}" ]]; then
    mkdir -p "${BACKUP_DIR}$(dirname "${path}")"
    cp -a "${path}" "${BACKUP_DIR}${path}"
  fi
done

log "Downloading USA ${TARGET_VERSION} from GitHub"
curl -fL --retry 3 --retry-delay 2 \
  "${RELEASE_URL}" \
  -o "${WORK_DIR}/UltraSkellyAdvanced-${TARGET_VERSION}-beta.zip"

log "Verifying release checksum"
ACTUAL_SHA256="$(sha256sum "${WORK_DIR}/UltraSkellyAdvanced-${TARGET_VERSION}-beta.zip" | awk '{print $1}')"
if [[ "${ACTUAL_SHA256}" != "${EXPECTED_SHA256}" ]]; then
  fail "Checksum mismatch. Expected ${EXPECTED_SHA256}, received ${ACTUAL_SHA256}. Nothing was installed."
fi

log "Extracting verified release"
python3 -m zipfile -e \
  "${WORK_DIR}/UltraSkellyAdvanced-${TARGET_VERSION}-beta.zip" \
  "${WORK_DIR}/source"

[[ -f "${WORK_DIR}/source/pyproject.toml" ]] || fail "Downloaded release is missing pyproject.toml."
[[ -x "${WORK_DIR}/source/deploy/bootstrap-pi.sh" || -f "${WORK_DIR}/source/deploy/bootstrap-pi.sh" ]] || fail "Downloaded release is missing bootstrap-pi.sh."

grep -Eq '^version[[:space:]]*=[[:space:]]*"0\.25\.6"[[:space:]]*$' "${WORK_DIR}/source/pyproject.toml" \
  || fail "Downloaded package does not identify itself as USA ${TARGET_VERSION}."

log "Installing updater-enabled USA ${TARGET_VERSION}"
export USA_UPDATE_INSTALL=1
export USA_INSTALLING_USER="${INSTALLING_USER}"
bash "${WORK_DIR}/source/deploy/bootstrap-pi.sh"

log "Waiting for USA ${TARGET_VERSION} health check"
observed=""
for _ in $(seq 1 30); do
  if payload="$(curl -fsS --max-time 3 http://127.0.0.1:8787/api/health 2>/dev/null)"; then
    observed="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("version", ""))' <<<"${payload}" 2>/dev/null || true)"
    if [[ "${observed}" == "${TARGET_VERSION}" ]]; then
      break
    fi
  fi
  sleep 2
done

if [[ "${observed}" != "${TARGET_VERSION}" ]]; then
  fail "USA did not come back healthy as ${TARGET_VERSION} (reported '${observed:-nothing}')."
fi

# The bridge backup is intentionally NOT written into update-rollback.json.
# Once on 0.25.6, all future updates use USA's normal managed rollback system.
cat > "${DATA_DIR}/bridge-status.json" <<JSON
{
  "state": "succeeded",
  "installed_version": "${TARGET_VERSION}",
  "legacy_backup_venv": "${BACKUP_VENV}",
  "message": "Legacy updater bridge completed successfully"
}
JSON
chmod 600 "${DATA_DIR}/bridge-status.json"

rm -rf "${WORK_DIR}"
trap - EXIT

printf '\n============================================================\n'
printf ' UltraSkellyAdvanced updater bridge completed successfully\n'
printf ' Installed version: %s\n' "${TARGET_VERSION}"
printf '============================================================\n\n'
printf 'The in-app Check for Updates / Install Update controls are now available.\n'
printf 'Owner settings under /var/lib/skelly-ai were preserved.\n'
printf 'Open: http://%s:8787\n' "$(hostname)"
printf '\n'
