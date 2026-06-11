# Realtime Test Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Emit a realtime `tests-events.json` under `$GENERIC_TESTS_WORKSPACE_DIR` as the suite runs, so the prod Validation Service can stream per-test status (with start/end timestamps) to its UI.

**Architecture:** A pytest-agnostic `EventRecorder` holds all logic (nodeid parsing, status precedence, timestamped JSON shaping, atomic writes) and is unit-tested directly. Two thin pytest hooks in `conftest.py` drive it. The whole thing is gated on `GENERIC_TESTS_WORKSPACE_DIR` (prod-only); in dev the hooks short-circuit to no-ops.

**Tech Stack:** Python 3.12, pytest 8.3.3, stdlib `json`/`datetime`/`os`. Tests run with `.venv/bin/python -m pytest`.

---

## File Structure

- **Modify** `src/drcc_validation/paths.py` — add `events_file() -> Path | None`, keyed on `GENERIC_TESTS_WORKSPACE_DIR` (not the `artifacts_dir()` fallback chain).
- **Create** `src/drcc_validation/runtime_events.py` — `EventRecorder`, the pure `outcome_status()` mapping, and timestamp/nodeid helpers. pytest-agnostic.
- **Create** `tests/test_runtime_events.py` — direct unit tests for the recorder + mapping, using a fake clock.
- **Modify** `tests/test_paths.py` — tests for `events_file()`.
- **Modify** `tests/conftest.py` — wire `pytest_runtest_logstart` / `pytest_runtest_logreport` to the recorder.

---

## Task 1: `events_file()` resolver

**Files:**
- Modify: `src/drcc_validation/paths.py`
- Test: `tests/test_paths.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_paths.py`:

```python
def test_events_file_none_when_workspace_unset(monkeypatch):
    monkeypatch.delenv("GENERIC_TESTS_WORKSPACE_DIR", raising=False)
    assert paths.events_file() is None


def test_events_file_none_when_workspace_empty(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "")
    assert paths.events_file() is None


def test_events_file_under_workspace_when_set(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "/workspace/job1")
    assert paths.events_file() == Path("/workspace/job1/tests-events.json")
```

(`paths` and `Path` are already imported at the top of `tests/test_paths.py`.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_paths.py -v`
Expected: FAIL — `AttributeError: module 'drcc_validation.paths' has no attribute 'events_file'`.

- [ ] **Step 3: Implement `events_file()`**

Append to `src/drcc_validation/paths.py`:

```python
def events_file() -> Path | None:
    """Realtime events file path, or None outside the prod framework.

    Generated only when GENERIC_TESTS_WORKSPACE_DIR is set; the Validation
    Service monitors this exact path (directly under the workspace dir).
    """
    workspace = os.environ.get("GENERIC_TESTS_WORKSPACE_DIR")
    if not workspace:
        return None
    return Path(workspace) / "tests-events.json"
```

(`os` and `Path` are already imported at the top of `paths.py`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_paths.py -v`
Expected: PASS — 9 passed (6 existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/paths.py tests/test_paths.py
git commit -m "feat: add events_file() resolver (prod-only, GENERIC_TESTS_WORKSPACE_DIR)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `EventRecorder` + `outcome_status`

**Files:**
- Create: `src/drcc_validation/runtime_events.py`
- Test: `tests/test_runtime_events.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_runtime_events.py`:

```python
import json
import re

import pytest

from drcc_validation.runtime_events import EventRecorder, outcome_status


class FakeClock:
    """Deterministic ISO-timestamp source; returns queued values, clamping to the last."""

    def __init__(self, *times):
        self._times = list(times) or ["1970-01-01T00:00:00.000Z"]
        self._i = 0

    def __call__(self):
        t = self._times[min(self._i, len(self._times) - 1)]
        self._i += 1
        return t


def test_running_sets_startTime_no_endTime(tmp_path):
    rec = EventRecorder(tmp_path / "tests-events.json",
                        now=FakeClock("2026-06-11T00:00:01.000Z"))
    rec.set_running("tests/test_limits_validation.py::test_x")
    [cat] = rec.to_dict()["testClassOrCategory"]
    assert cat["classOrCategoryName"] == "test_limits_validation"
    assert cat["testsEvents"] == [{
        "testName": "test_x",
        "testStatus": "RUNNING",
        "startTime": "2026-06-11T00:00:01.000Z",
    }]


def test_outcome_sets_endTime_keeps_startTime(tmp_path):
    rec = EventRecorder(tmp_path / "e.json",
                        now=FakeClock("2026-06-11T00:00:01.000Z", "2026-06-11T00:00:02.500Z"))
    rec.set_running("tests/test_x.py::test_y")
    rec.set_outcome("tests/test_x.py::test_y", "SUCCESSFUL")
    [ev] = rec.to_dict()["testClassOrCategory"][0]["testsEvents"]
    assert ev == {
        "testName": "test_y",
        "testStatus": "SUCCESSFUL",
        "startTime": "2026-06-11T00:00:01.000Z",
        "endTime": "2026-06-11T00:00:02.500Z",
    }


def test_class_category_from_nodeid(tmp_path):
    rec = EventRecorder(tmp_path / "e.json", now=FakeClock("t"))
    rec.set_running("tests/test_x.py::TestFoo::test_y")
    cat = rec.to_dict()["testClassOrCategory"][0]
    assert cat["classOrCategoryName"] == "TestFoo"
    assert cat["testsEvents"][0]["testName"] == "test_y"


def test_failed_is_sticky(tmp_path):
    rec = EventRecorder(tmp_path / "e.json", now=FakeClock("t1", "t2", "t3"))
    rec.set_running("tests/test_x.py::test_y")
    rec.set_outcome("tests/test_x.py::test_y", "FAILED")
    rec.set_outcome("tests/test_x.py::test_y", "SUCCESSFUL")  # must not downgrade
    ev = rec.to_dict()["testClassOrCategory"][0]["testsEvents"][0]
    assert ev["testStatus"] == "FAILED"


def test_multiple_categories_preserve_discovery_order(tmp_path):
    rec = EventRecorder(tmp_path / "e.json", now=FakeClock("t"))
    rec.set_running("tests/test_b.py::test_1")
    rec.set_running("tests/test_a.py::test_2")
    names = [c["classOrCategoryName"] for c in rec.to_dict()["testClassOrCategory"]]
    assert names == ["test_b", "test_a"]


def test_write_produces_valid_json_matching_to_dict(tmp_path):
    path = tmp_path / "tests-events.json"
    rec = EventRecorder(path, now=FakeClock("t1", "t2"))
    rec.set_running("tests/test_x.py::test_y")
    rec.set_outcome("tests/test_x.py::test_y", "SUCCESSFUL")
    assert path.exists()
    assert json.loads(path.read_text()) == rec.to_dict()


def test_write_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "tests-events.json"
    rec = EventRecorder(path, now=FakeClock("t"))
    rec.set_running("tests/test_x.py::test_y")
    assert path.exists()


def test_default_timestamp_format(tmp_path):
    rec = EventRecorder(tmp_path / "e.json")  # real clock
    rec.set_running("tests/test_x.py::test_y")
    ts = rec.to_dict()["testClassOrCategory"][0]["testsEvents"][0]["startTime"]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)


@pytest.mark.parametrize("when,outcome,expected", [
    ("setup", "passed", None),
    ("setup", "skipped", "SKIPPED"),
    ("setup", "failed", "FAILED"),
    ("call", "passed", "SUCCESSFUL"),
    ("call", "skipped", "SKIPPED"),
    ("call", "failed", "FAILED"),
    ("teardown", "passed", None),
    ("teardown", "failed", "FAILED"),
])
def test_outcome_status_mapping(when, outcome, expected):
    assert outcome_status(when, outcome) == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_runtime_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drcc_validation.runtime_events'` (collection error).

- [ ] **Step 3: Implement the module**

Create `src/drcc_validation/runtime_events.py`:

```python
"""Realtime per-test event recorder for the prod Generic Tests framework.

Atomically rewrites a tests-events.json that the Validation Service monitors.
This module is pytest-agnostic so it can be unit-tested directly; the pytest
hooks in tests/conftest.py extract primitives from reports and drive it.
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    """ISO 8601 UTC, millisecond precision: yyyy-MM-ddTHH:mm:ss.SSSZ."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _split_nodeid(nodeid: str) -> tuple[str, str]:
    """(category, testName) from a pytest nodeid.

    'tests/test_x.py::test_y'        -> ('test_x', 'test_y')   # module stem
    'tests/test_x.py::TestC::test_y' -> ('TestC', 'test_y')    # class
    """
    parts = nodeid.split("::")
    test_name = parts[-1]
    category = parts[-2] if len(parts) >= 3 else Path(parts[0]).stem
    return category, test_name


def outcome_status(when: str, outcome: str) -> str | None:
    """Map a pytest phase report to a terminal status, or None for no change.

    when ∈ {setup, call, teardown}; outcome ∈ {passed, failed, skipped}.
    """
    if outcome == "failed":
        return "FAILED"
    if outcome == "skipped" and when in ("setup", "call"):
        return "SKIPPED"
    if when == "call" and outcome == "passed":
        return "SUCCESSFUL"
    return None


class EventRecorder:
    """Accumulates test events and atomically rewrites the JSON file on change."""

    def __init__(self, path, now=_utc_now_iso):
        self._path = Path(path)
        self._now = now
        # category -> testName -> event dict
        self._events: "OrderedDict[str, OrderedDict[str, dict]]" = OrderedDict()

    def set_running(self, nodeid: str) -> None:
        event = self._event(nodeid)
        event["testStatus"] = "RUNNING"
        if "startTime" not in event:
            event["startTime"] = self._now()
        self._write()

    def set_outcome(self, nodeid: str, status: str) -> None:
        event = self._event(nodeid)
        if event.get("testStatus") != "FAILED":  # FAILED is sticky
            event["testStatus"] = status
        if "startTime" not in event:
            event["startTime"] = self._now()
        event["endTime"] = self._now()
        self._write()

    def to_dict(self) -> dict:
        return {
            "testClassOrCategory": [
                {
                    "classOrCategoryName": category,
                    "testsEvents": [self._ordered(e) for e in tests.values()],
                }
                for category, tests in self._events.items()
            ]
        }

    def _event(self, nodeid: str) -> dict:
        category, test_name = _split_nodeid(nodeid)
        tests = self._events.setdefault(category, OrderedDict())
        return tests.setdefault(test_name, {"testName": test_name})

    @staticmethod
    def _ordered(event: dict) -> dict:
        """Stable key order: testName, testStatus, startTime, endTime."""
        out = {"testName": event["testName"], "testStatus": event.get("testStatus")}
        if "startTime" in event:
            out["startTime"] = event["startTime"]
        if "endTime" in event:
            out["endTime"] = event["endTime"]
        return out

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        os.replace(tmp, self._path)  # atomic rename — never a partial read
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_runtime_events.py -v`
Expected: PASS — 16 passed (8 functions + 8 parametrized mapping cases).

- [ ] **Step 5: Run the full non-integration suite**

Run: `.venv/bin/python -m pytest -m "not integration" -q`
Expected: PASS — 53 passed, 3 deselected (37 after Task 1 + 16 new).

- [ ] **Step 6: Commit**

```bash
git add src/drcc_validation/runtime_events.py tests/test_runtime_events.py
git commit -m "feat: EventRecorder for realtime tests-events.json

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the pytest hooks in conftest

**Files:**
- Modify: `tests/conftest.py`

The hooks are gated on `events_file()` (None in dev → no-op), so there is no committed nested-pytest test; verification is the full suite staying green plus a one-off manual smoke run with the env var set.

- [ ] **Step 1: Replace `tests/conftest.py`**

The current file is:

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

Replace its ENTIRE content with (the `sys.path` insertion MUST stay first, before importing `drcc_validation`):

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import logging

from drcc_validation.paths import events_file
from drcc_validation.runtime_events import EventRecorder, outcome_status

logger = logging.getLogger("drcc_validation.events")

# Prod-only: a path exists only when GENERIC_TESTS_WORKSPACE_DIR is set.
_events_path = events_file()
_recorder = EventRecorder(_events_path) if _events_path else None


def _record_safely(fn, *args):
    """Event logging must never break the test run — the tests are the point."""
    try:
        fn(*args)
    except Exception:  # noqa: BLE001
        logger.warning("failed to record realtime test event", exc_info=True)


def pytest_runtest_logstart(nodeid, location):
    if _recorder is not None:
        _record_safely(_recorder.set_running, nodeid)


def pytest_runtest_logreport(report):
    if _recorder is None:
        return
    status = outcome_status(report.when, report.outcome)
    if status is not None:
        _record_safely(_recorder.set_outcome, report.nodeid, status)
```

- [ ] **Step 2: Confirm the full non-integration suite still passes (no-op path)**

Run: `.venv/bin/python -m pytest -m "not integration" -q`
Expected: PASS — 53 passed, 3 deselected. (Confirms conftest imports cleanly and the hooks no-op when `GENERIC_TESTS_WORKSPACE_DIR` is unset.)

- [ ] **Step 3: Manual smoke — prove the hooks emit a valid file when the env var is set**

```bash
rm -rf /tmp/evttest && mkdir -p /tmp/evttest
GENERIC_TESTS_WORKSPACE_DIR=/tmp/evttest .venv/bin/python -m pytest tests/test_paths.py -q
.venv/bin/python -c "import json; d=json.load(open('/tmp/evttest/tests-events.json')); cats=d['testClassOrCategory']; assert cats[0]['classOrCategoryName']=='test_paths'; ev=cats[0]['testsEvents'][0]; assert ev['testStatus'] in ('SUCCESSFUL','SKIPPED','FAILED'); assert 'startTime' in ev and 'endTime' in ev; print('OK', len(cats[0]['testsEvents']), 'events;', ev)"
```

Expected: pytest runs `test_paths` (9 passed), then the python check prints `OK 9 events; {...}` — confirming the file was written under `$GENERIC_TESTS_WORKSPACE_DIR`, grouped by module (`test_paths`), with terminal statuses and both timestamps.

(Note: `test_events_file_*` tests monkeypatch the env var within their own scope; that does not affect the session recorder created at conftest import, so this smoke run is unaffected.)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "feat: drive EventRecorder from pytest hooks (prod-only)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] **Run the complete non-integration suite once more**

Run: `.venv/bin/python -m pytest -m "not integration" -q`
Expected: PASS — 53 passed, 3 deselected.

- [ ] **Confirm the integration suite still collects**

Run: `.venv/bin/python -m pytest tests/test_limits_validation.py --collect-only -q`
Expected: 3 tests collected, no errors.
