#!/bin/sh
set -eu

# Resources (manifest/config) load via paths relative to /app. The prod
# framework sets the container working dir to the workspace dir, so reset CWD
# to /app here; artifacts are still written to the absolute base resolved below.
cd /app

# Ad-hoc override: any args are passed straight to pytest, e.g.
# `docker run <img> -m "not integration" -v` for no-OCI verification.
if [ "$#" -gt 0 ]; then
    exec python -m pytest "$@"
fi

# Default (prod): resolve the artifacts base, mirroring
# drcc_validation.paths.artifacts_dir() precedence, then emit reports + JUnit there.
BASE="${GENERIC_TESTS_WORKSPACE_DIR:-${OUTPUT_DIR:-output}}"
mkdir -p "$BASE/reports" "$BASE/logs"
exec python -m pytest -v -m integration --junitxml="$BASE/logs/results.xml"
