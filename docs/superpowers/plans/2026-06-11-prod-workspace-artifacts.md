# Prod Workspace Artifacts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write the four customer reports and the JUnit results under `GENERIC_TESTS_WORKSPACE_DIR` when present, so prod artifacts survive container exit and appear in the Validation Service UI.

**Architecture:** A single resolver module owns the output-location precedence (`GENERIC_TESTS_WORKSPACE_DIR` → `OUTPUT_DIR` → `output`). Reports go to a `reports/` subdir, JUnit XML to a `logs/` subdir. A thin shell entrypoint mirrors the same precedence for the pytest `--junitxml` path and resets CWD to `/app` so relative resource lookups keep working under the prod framework's workspace working directory.

**Tech Stack:** Python 3.12, pytest 8.3.3, Docker (python:3.12-slim). Tests run with `.venv/bin/python -m pytest`.

---

## File Structure

- **Create** `src/drcc_validation/paths.py` — resolver: `artifacts_dir()`, `reports_dir()`, `logs_dir()`. Single source of truth for the precedence.
- **Create** `tests/test_paths.py` — unit tests for the precedence and subdir helpers.
- **Modify** `src/drcc_validation/cli.py` — `run_validation` writes reports into `<base>/reports`; `main()`'s `--output` default comes from `artifacts_dir()`.
- **Modify** `tests/test_cli.py` — assert report files under `tmp_path / "reports"`.
- **Modify** `tests/test_limits_validation.py` — resolve via `paths`, assert under `reports_dir()`.
- **Create** `docker-entrypoint.sh` — `cd /app`, resolve base, create `reports/`+`logs/`, exec pytest with JUnit pointed at `logs/`.
- **Modify** `Dockerfile` — copy + chmod the entrypoint, replace the hardcoded `CMD` with `ENTRYPOINT`.

No change to `docker-compose.yml`: `OUTPUT_DIR=/app/output` (Dockerfile `ENV`) keeps the base at `/app/output`, and the existing `./output:/app/output` mount now receives `reports/` and `logs/` subdirs.

---

## Task 1: Path resolver module

**Files:**
- Create: `src/drcc_validation/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_paths.py`:

```python
from pathlib import Path

from drcc_validation import paths


def test_workspace_var_takes_precedence(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "/workspace/job1")
    monkeypatch.setenv("OUTPUT_DIR", "/app/output")
    assert paths.artifacts_dir() == Path("/workspace/job1")


def test_falls_back_to_output_dir(monkeypatch):
    monkeypatch.delenv("GENERIC_TESTS_WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("OUTPUT_DIR", "/app/output")
    assert paths.artifacts_dir() == Path("/app/output")


def test_defaults_to_output(monkeypatch):
    monkeypatch.delenv("GENERIC_TESTS_WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    assert paths.artifacts_dir() == Path("output")


def test_empty_workspace_var_falls_back(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "")
    monkeypatch.setenv("OUTPUT_DIR", "/app/output")
    assert paths.artifacts_dir() == Path("/app/output")


def test_reports_and_logs_subdirs(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "/workspace/job1")
    assert paths.reports_dir() == Path("/workspace/job1/reports")
    assert paths.logs_dir() == Path("/workspace/job1/logs")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_paths.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drcc_validation.paths'` (collection error).

- [ ] **Step 3: Write the resolver**

Create `src/drcc_validation/paths.py`:

```python
"""Resolve where run artifacts are written, preferring the prod workspace volume.

Precedence (highest first):
  GENERIC_TESTS_WORKSPACE_DIR  — set by the prod Generic Tests framework
  OUTPUT_DIR                   — dev / docker-compose
  "output"                     — local default (cwd-relative)
"""
from __future__ import annotations

import os
from pathlib import Path


def artifacts_dir() -> Path:
    """Base directory for all run artifacts."""
    return Path(
        os.environ.get("GENERIC_TESTS_WORKSPACE_DIR")
        or os.environ.get("OUTPUT_DIR")
        or "output"
    )


def reports_dir() -> Path:
    """Where the customer reports are written."""
    return artifacts_dir() / "reports"


def logs_dir() -> Path:
    """Where run logs / JUnit results are written."""
    return artifacts_dir() / "logs"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_paths.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/paths.py tests/test_paths.py
git commit -m "feat: add artifacts-dir resolver honoring GENERIC_TESTS_WORKSPACE_DIR

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Write reports into a `reports/` subdirectory

**Files:**
- Modify: `src/drcc_validation/cli.py:30-83`
- Test: `tests/test_cli.py:28-31`

- [ ] **Step 1: Update the unit-test assertions to expect the `reports/` subdir (failing)**

In `tests/test_cli.py`, replace the four existence assertions (currently lines 28-31):

```python
    assert (tmp_path / "DRCC-Region-Readiness-Report.html").exists()
    assert (tmp_path / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (tmp_path / "Validation-Limits-Report.pdf").exists()
    assert (tmp_path / "Validation-Limits-Report.html").exists()
```

with:

```python
    reports = tmp_path / "reports"
    assert (reports / "DRCC-Region-Readiness-Report.html").exists()
    assert (reports / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (reports / "Validation-Limits-Report.pdf").exists()
    assert (reports / "Validation-Limits-Report.html").exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL — the reports are still written to `tmp_path` directly, so `tmp_path/reports/...` does not exist.

- [ ] **Step 3: Update `cli.py` to write into `<base>/reports` and default `--output` from the resolver**

In `src/drcc_validation/cli.py`, add the import near the other relative imports (after line 11, the `from .config import ...` line):

```python
from .paths import artifacts_dir
```

Replace the top of `run_validation` (currently lines 33-34):

```python
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
```

with:

```python
    reports = Path(output_dir) / "reports"
    reports.mkdir(parents=True, exist_ok=True)
```

Replace the four render calls and the log line (currently lines 69-73):

```python
    render_readiness_html(summary, cfg, output_dir / "DRCC-Region-Readiness-Report.html")
    render_readiness_pdf(summary, cfg, output_dir / "DRCC-Region-Readiness-Report.pdf")
    render_validate_limits_pdf(summary, meta, output_dir / "Validation-Limits-Report.pdf")
    render_validate_limits_html(summary, meta, output_dir / "Validation-Limits-Report.html")
    logger.info("Reports written to %s", output_dir)
```

with:

```python
    render_readiness_html(summary, cfg, reports / "DRCC-Region-Readiness-Report.html")
    render_readiness_pdf(summary, cfg, reports / "DRCC-Region-Readiness-Report.pdf")
    render_validate_limits_pdf(summary, meta, reports / "Validation-Limits-Report.pdf")
    render_validate_limits_html(summary, meta, reports / "Validation-Limits-Report.html")
    logger.info("Reports written to %s", reports)
```

Replace the `--output` argument default (currently line 79):

```python
    parser.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "output"))
```

with:

```python
    parser.add_argument("--output", default=str(artifacts_dir()))
```

- [ ] **Step 4: Run the unit test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: PASS — `test_run_validation_produces_reports` passes.

- [ ] **Step 5: Run the full non-integration suite to confirm nothing regressed**

Run: `.venv/bin/python -m pytest -m "not integration" -q`
Expected: PASS — 33 passed, 3 deselected (28 prior + 5 new from Task 1).

- [ ] **Step 6: Commit**

```bash
git add src/drcc_validation/cli.py tests/test_cli.py
git commit -m "feat: write reports into reports/ subdir of the artifacts base

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Point the integration test at the resolved artifacts dir

**Files:**
- Modify: `tests/test_limits_validation.py:6-25`

The `integration` test requires live OCI auth and is not run locally; verification here is import/collection plus the non-integration suite staying green.

- [ ] **Step 1: Rewrite the imports, base resolution, and report assertions**

Replace the top of `tests/test_limits_validation.py` (currently lines 6-18):

```python
import os
from pathlib import Path

import pytest

from drcc_validation.cli import run_validation

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))


@pytest.fixture(scope="module")
def summary():
    return run_validation(OUTPUT_DIR)
```

with:

```python
import pytest

from drcc_validation.cli import run_validation
from drcc_validation.paths import artifacts_dir, reports_dir

BASE = artifacts_dir()


@pytest.fixture(scope="module")
def summary():
    return run_validation(BASE)
```

Replace the three existence assertions in `test_reports_are_generated` (currently lines 23-25):

```python
    assert (OUTPUT_DIR / "DRCC-Region-Readiness-Report.html").exists()
    assert (OUTPUT_DIR / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (OUTPUT_DIR / "Validation-Limits-Report.pdf").exists()
```

with:

```python
    assert (reports_dir() / "DRCC-Region-Readiness-Report.html").exists()
    assert (reports_dir() / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (reports_dir() / "Validation-Limits-Report.pdf").exists()
```

Leave `test_some_limits_were_checked` and `test_no_limit_errors_when_strict` unchanged (the relative `load_report_config("config/report_config.yaml")` is handled by the entrypoint's `cd /app` in the container, and by the repo-root CWD locally).

- [ ] **Step 2: Verify the file imports and collects cleanly**

Run: `.venv/bin/python -m pytest tests/test_limits_validation.py --collect-only -q`
Expected: 3 tests collected (`test_reports_are_generated`, `test_some_limits_were_checked`, `test_no_limit_errors_when_strict`), no import errors.

- [ ] **Step 3: Confirm the non-integration suite is still green**

Run: `.venv/bin/python -m pytest -m "not integration" -q`
Expected: PASS — 33 passed, 3 deselected.

- [ ] **Step 4: Commit**

```bash
git add tests/test_limits_validation.py
git commit -m "test: resolve integration-test artifacts dir via paths module

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Entrypoint script + Dockerfile

**Files:**
- Create: `docker-entrypoint.sh`
- Modify: `Dockerfile:13-24`

- [ ] **Step 1: Create the entrypoint script**

Create `docker-entrypoint.sh`:

```sh
#!/bin/sh
set -e

# Resources (manifest/config) load via paths relative to /app. The prod
# framework sets the container working dir to the workspace dir, so reset CWD
# to /app here; artifacts are still written to the absolute base resolved below.
cd /app

# Mirror drcc_validation.paths.artifacts_dir() precedence.
BASE="${GENERIC_TESTS_WORKSPACE_DIR:-${OUTPUT_DIR:-output}}"
mkdir -p "$BASE/reports" "$BASE/logs"

exec pytest -v -m integration --junitxml="$BASE/logs/results.xml"
```

- [ ] **Step 2: Verify the script is valid POSIX shell**

Run: `sh -n docker-entrypoint.sh`
Expected: no output, exit code 0.

- [ ] **Step 3: Update the Dockerfile**

In `Dockerfile`, replace the block from the `COPY tests/` line through the end (currently lines 17-24):

```dockerfile
COPY tests/ ./tests/

ENV PYTHONPATH=/app/src
ENV OCI_ENV=dev
ENV OUTPUT_DIR=/app/output

# Run the full suite incl. the live integration test; emit JUnit + reports.
CMD ["pytest", "-v", "-m", "integration", "--junitxml=/app/output/results.xml"]
```

with:

```dockerfile
COPY tests/ ./tests/
COPY docker-entrypoint.sh .
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONPATH=/app/src
ENV OCI_ENV=dev
ENV OUTPUT_DIR=/app/output

# Entrypoint resolves the artifacts base (workspace dir in prod), creates
# reports/ + logs/, and runs the live integration suite emitting JUnit + reports.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
```

- [ ] **Step 4: Build the image**

Run: `docker build -t drcc-validate:test .`
Expected: build succeeds; final step tags `drcc-validate:test`.

- [ ] **Step 5: Smoke-test the entrypoint's dir resolution inside the image**

This verifies `cd /app`, the precedence, and subdir creation without needing OCI auth (it overrides the entrypoint with `sh` and runs only the resolution lines):

```bash
rm -rf /tmp/wstest && mkdir -p /tmp/wstest
docker run --rm \
  -e GENERIC_TESTS_WORKSPACE_DIR=/workspace \
  -v /tmp/wstest:/workspace \
  --entrypoint sh drcc-validate:test \
  -c 'cd /app; BASE="${GENERIC_TESTS_WORKSPACE_DIR:-${OUTPUT_DIR:-output}}"; mkdir -p "$BASE/reports" "$BASE/logs"; echo "BASE=$BASE PWD=$(pwd)"; ls -R /workspace'
```

Expected output includes:
```
BASE=/workspace PWD=/app
/workspace:
logs
reports
```
(`/tmp/wstest` on the host now contains empty `reports/` and `logs/` dirs.)

> **Note:** A full live run (`docker run` with real resource-principal/OCI auth) is required to confirm the reports and `results.xml` are actually produced — that cannot be exercised locally without prod auth. This step verifies the path/CWD logic only.

- [ ] **Step 6: Commit**

```bash
git add docker-entrypoint.sh Dockerfile
git commit -m "feat: entrypoint writes JUnit + reports under workspace dir in prod

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the complete non-integration suite once more**

Run: `.venv/bin/python -m pytest -m "not integration" -q`
Expected: PASS — 33 passed, 3 deselected.

- [ ] **Confirm the integration suite still collects**

Run: `.venv/bin/python -m pytest tests/test_limits_validation.py --collect-only -q`
Expected: 3 tests collected, no errors.
