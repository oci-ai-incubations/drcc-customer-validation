# Prod Workspace Artifacts — Write Output to `GENERIC_TESTS_WORKSPACE_DIR`

**Date:** 2026-06-11
**Status:** Approved (design)

## Purpose

When the validation container runs in the production Generic Tests framework,
every artifact worth keeping (the four customer reports and the JUnit results)
must land under the framework-mounted **workspace directory** so they survive
container exit and appear in the Validation Service UI as the Job's Artifacts
Directory. Anything written outside that volume in prod is lost when the
container exits.

Today output is keyed off `OUTPUT_DIR` (default `output`, set to `/app/output`
in the Dockerfile) and the JUnit path is hardcoded in the Dockerfile `CMD` as
`/app/output/results.xml`. In prod there is no bind mount at `/app/output`, so
those artifacts disappear.

## Contract from the framework

- Each Job runs in a container with a mounted **workspace volume**.
- Its full path is in the env var `GENERIC_TESTS_WORKSPACE_DIR`.
- Files placed in that directory (or subdirectories) become the Job's Artifacts
  Directory in the UI after the container exits.
- The framework sets the container's **working directory** to the workspace
  directory.

## Design

### 1. Output-location precedence

Resolve the artifacts base directory in priority order, the env var's presence
being the prod signal (no separate `OCI_ENV` check):

```
GENERIC_TESTS_WORKSPACE_DIR  ->  OUTPUT_DIR  ->  "output"
```

### 2. Single path resolver — new `src/drcc_validation/paths.py`

One module owns the precedence, used by both the app and the test:

```python
def artifacts_dir() -> Path:   # GENERIC_TESTS_WORKSPACE_DIR -> OUTPUT_DIR -> "output"
def reports_dir() -> Path:     # artifacts_dir() / "reports"
def logs_dir() -> Path:        # artifacts_dir() / "logs"
```

### 3. Artifact layout (subdirectories)

```
<artifacts base>/
  reports/   DRCC-Region-Readiness-Report.{pdf,html}
             Validation-Limits-Report.{pdf,html}
  logs/      results.xml
```

### 4. `src/drcc_validation/cli.py`

- `run_validation(output_dir, ...)` treats `output_dir` as the **base**; it
  writes the four reports into `output_dir / "reports"`, creating it.
- `main()`'s `--output` default comes from `artifacts_dir()`; the `--output`
  flag still overrides.

### 5. `tests/test_limits_validation.py`

- Drop the local `OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))`
  constant; resolve via the new module.
- Assertions check for the report files under `reports_dir()`.

### 6. Entrypoint — new `docker-entrypoint.sh`

pytest generates `results.xml`, but the workspace path is only known at runtime,
so the JUnit path cannot stay hardcoded in the Dockerfile. A thin entrypoint
resolves the base with the same precedence and points pytest at `logs/`:

```sh
#!/bin/sh
set -e
cd /app                                          # CWD safety — see section 8
BASE="${GENERIC_TESTS_WORKSPACE_DIR:-${OUTPUT_DIR:-output}}"
mkdir -p "$BASE/reports" "$BASE/logs"
exec pytest -v -m integration --junitxml="$BASE/logs/results.xml"
```

The shell precedence intentionally mirrors the Python resolver; both read the
same env vars, so they always agree.

### 7. `Dockerfile`

- `COPY docker-entrypoint.sh .` and make it executable.
- Replace the hardcoded `CMD ["pytest", ..., "--junitxml=/app/output/results.xml"]`
  with `ENTRYPOINT ["/app/docker-entrypoint.sh"]`.
- Leave `ENV OUTPUT_DIR=/app/output` so dev/compose behavior is unchanged.

### 8. CWD safety (Option A)

The framework sets the container working directory to the workspace directory,
but the code loads `manifest/Default_Limits.xlsx` and
`config/report_config.yaml` via **relative** paths that only resolve from
`/app`. The `cd /app` in the entrypoint resets the working directory before
pytest runs, so resources are read from `/app` while artifacts are written to
the absolute workspace path. This also covers the test's hardcoded relative
`load_report_config("config/report_config.yaml")`, which an absolute-path change
in `cli.py` alone would not fix.

## Behavior matrix

| Environment | `GENERIC_TESTS_WORKSPACE_DIR` | Base resolves to | Artifacts persist via |
|-------------|-------------------------------|------------------|-----------------------|
| Prod (framework) | set, e.g. `/workspace/<job>` | that path | workspace volume → UI |
| Dev (`docker compose up`) | unset | `/app/output` (from `OUTPUT_DIR`) | `./output` bind mount |
| Local pytest | unset | `output` (cwd-relative) | local filesystem |

## Out of scope (YAGNI)

- No file-based application log capture. Container stdout still carries the run
  log, and `results.xml` populates `logs/`. A `.log` file can be added later if
  the UI needs one.
- No change to auth, validation logic, or report contents.
