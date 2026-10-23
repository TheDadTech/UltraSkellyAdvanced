#!/usr/bin/env bash
set -Eeuo pipefail

# Offline recovery for an owner-selected official release. Never defaults to a downgrade.
if [[ $# -ne 3 ]]; then
  echo "Usage: sudo bash $0 VERSION /absolute/path/to/release.zip PUBLISHED_SHA256" >&2
  exit 2
fi
TARGET_VERSION="$1"
RELEASE_ARCHIVE="$2"
EXPECTED_SHA256="${3,,}"
[[ "$TARGET_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$ ]] || { echo "Invalid version" >&2; exit 2; }
[[ "$EXPECTED_SHA256" =~ ^[0-9a-f]{64}$ && -f "$RELEASE_ARCHIVE" ]] || { echo "Provide a release ZIP and its published checksum" >&2; exit 2; }
RELEASE_ARCHIVE="$(realpath "$RELEASE_ARCHIVE")"
ACTUAL_SHA256="$(sha256sum "$RELEASE_ARCHIVE" | awk '{print $1}')"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || { echo "Checksum mismatch. Nothing was changed." >&2; exit 1; }
DATA_DIR="/var/lib/skelly-ai"
RECOVERY_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
WORK_DIR="${DATA_DIR}/bridge-work-${RECOVERY_ID}"
BACKUP_DIR="${DATA_DIR}/bridge-backup-${RECOVERY_ID}"
ACTIVE_VENV="/opt/skelly-ai/venv"
BACKUP_VENV="/opt/skelly-ai/venv.pre-updater-bridge-${RECOVERY_ID}"

log() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

if [[ ${EUID} -ne 0 ]]; then
  fail "Run the documented recovery command with sudo, a local ZIP, version and published checksum"
fi

command -v curl >/dev/null 2>&1 || fail "curl is required for the final local health check."
command -v python3 >/dev/null 2>&1 || fail "python3 is required."
command -v sha256sum >/dev/null 2>&1 || fail "sha256sum is required."

if [[ -x "${ACTIVE_VENV}/bin/python" ]]; then
  INSTALLED_VERSION="$("${ACTIVE_VENV}/bin/python" -c 'from skelly_ai import __version__; print(__version__)')"
  python3 - "$INSTALLED_VERSION" "$TARGET_VERSION" <<'CHECK_VERSION'
import re, sys
# Conservative release comparison: recovery never installs an older or identical base version.
def base(v):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    if not match:
        raise SystemExit("Cannot determine installed version; use the normal updater or seek support")
    return tuple(map(int, match.groups()))
if base(sys.argv[2]) <= base(sys.argv[1]):
    raise SystemExit("Recovery requires a newer release. Use USA's rollback control for a previous version.")
CHECK_VERSION
fi

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

log "Validating and extracting the owner-verified release"
python3 - "$RELEASE_ARCHIVE" "${WORK_DIR}/source" "$TARGET_VERSION" <<'VALIDATE_ZIP'
import pathlib, stat, sys, tomllib, zipfile
archive, destination, version = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
if archive.stat().st_size > 150 * 1024**2:
    raise SystemExit("ZIP exceeds 150 MiB")
with zipfile.ZipFile(archive) as bundle:
    members = bundle.infolist()
    if len(members) > 5000 or sum(m.file_size for m in members) > 350 * 1024**2:
        raise SystemExit("ZIP expands beyond the allowed size")
    seen = set()
    for member in members:
        path = pathlib.PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or "\\" in member.filename or member.filename in seen or stat.S_ISLNK(member.external_attr >> 16):
            raise SystemExit("Unsafe ZIP entry")
        seen.add(member.filename)
    # Release packages have a flat root, as produced by package-release.sh.
    metadata = tomllib.loads(bundle.read("pyproject.toml").decode())
    if metadata.get("project", {}).get("name") != "skelly-ai" or metadata["project"].get("version") != version:
        raise SystemExit("ZIP does not match the requested USA release")
    for required in ("deploy/bootstrap-pi.sh", "deploy/usa-system-helper.py", "src/skelly_ai/api.py"):
        if required not in seen:
            raise SystemExit("Incomplete USA release")
    bundle.extractall(destination)
VALIDATE_ZIP

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
# Once recovered, all future updates use USA's normal managed rollback system.
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
