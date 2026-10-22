#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TEST_DATA_DIR="$(mktemp -d /tmp/usa-dev-tests.XXXXXX)"
trap 'rm -rf -- "$TEST_DATA_DIR"' EXIT

export SKELLY_ENV_FILE=/dev/null
export SKELLY_DATA_DIR="$TEST_DATA_DIR"
export SKELLY_SIMULATION=true

if [[ -x .venv/bin/python ]]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi

"$PYTHON" -m pytest "$@"
