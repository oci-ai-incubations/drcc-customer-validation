#!/bin/sh
set -eu

# Resources (manifest/config) load via paths relative to /app. The prod
# framework sets the container working dir to the workspace dir, so reset CWD
# to /app here; artifacts are still written to the absolute base resolved below.
cd /app

# Mirror drcc_validation.paths.artifacts_dir() precedence.
BASE="${GENERIC_TESTS_WORKSPACE_DIR:-${OUTPUT_DIR:-output}}"
mkdir -p "$BASE/reports" "$BASE/logs"

exec python -m pytest -v -m integration --junitxml="$BASE/logs/results.xml"
