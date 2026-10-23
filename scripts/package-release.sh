#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUTPUT_DIRECTORY="${2:-$(dirname "$PROJECT_ROOT")}"

version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$PROJECT_ROOT/pyproject.toml" | head -n1)"
[[ -n "$version" ]] || { echo "Unable to read project version" >&2; exit 1; }

base_name="UltraSkellyAdvanced-$version"
destination="$OUTPUT_DIRECTORY/$base_name.zip"
checksum_path="$destination.sha256"
staging="$(mktemp -d)"

cleanup() { rm -rf "$staging"; }
trap cleanup EXIT

for directory in deploy docs image releases scripts tests; do
  cp -a "$PROJECT_ROOT/$directory" "$staging/"
done
mkdir -p "$staging/src"
cp -a "$PROJECT_ROOT/src/skelly_ai" "$staging/src/"

for file in   "install-updater-bridge.sh"   ".gitignore"   "Banner Image.png"   "DISTRIBUTION.md"   "NOTICE.md"   "pyproject.toml"   "QUICK_START.md"   "README.md"   "RELEASE_NOTES.md"; do
  cp -a "$PROJECT_ROOT/$file" "$staging/"
done

find "$staging" -type d \( -name __pycache__ -o -name .pytest_cache -o -name .git \) -prune -exec rm -rf {} +
find "$staging" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.bak' -o -name '*.tmp' \) -delete

[[ ! -e "$destination" && ! -e "$checksum_path" ]] || { echo "Refusing to overwrite existing release artifacts" >&2; exit 1; }
(
  cd "$staging"
  zip -qr "$destination" .
)

hash="$(sha256sum "$destination" | awk '{print $1}')"
printf '%s  %s\n' "$hash" "$base_name.zip" > "$checksum_path"

echo "Archive: $destination"
echo "Checksum: $checksum_path"
echo "SHA-256: $hash"
