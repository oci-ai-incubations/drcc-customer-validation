# Realtime Test Events — `tests-events.json` for the Validation Service UI

**Date:** 2026-06-11
**Status:** Approved (design)

## Purpose

Emit a realtime `tests-events.json` file as the suite runs so the production
Generic Tests framework's Validation Service can monitor it and stream
per-test status to its UI. The file is rewritten on every test state change
(start and completion), giving live progress.

This is the "Generate ALL Runtime Events" option: one event per test, every
test, grouped by test class/category.

## Prod-only gating

Events are generated **only** when `GENERIC_TESTS_WORKSPACE_DIR` is set (the
prod framework signal and the directory the Validation Service monitors). In
dev / local / `docker compose` / CI unit runs the var is unset, no file is
written, and the pytest hooks short-circuit to no-ops with zero overhead.

This keys specifically on `GENERIC_TESTS_WORKSPACE_DIR`, **not** the general
`artifacts_dir()` fallback chain (`OUTPUT_DIR` / `output`), so it is prod-only
by construction.

## File location

`$GENERIC_TESTS_WORKSPACE_DIR/tests-events.json` — placed directly under the
workspace base (NOT in the `reports/` or `logs/` subdirs), per the framework
contract.

## File format

JSON, matching the framework's documented schema plus per-event timestamps:

```json
{
  "testClassOrCategory": [
    {
      "classOrCategoryName": "test_limits_validation",
      "testsEvents": [
        {
          "testName": "test_reports_are_generated",
          "testStatus": "SUCCESSFUL",
          "startTime": "2026-06-11T14:23:45.120Z",
          "endTime": "2026-06-11T14:23:47.880Z"
        }
      ]
    }
  ]
}
```

- `classOrCategoryName`, `testsEvents` ordered by discovery order.
- `testStatus` ∈ `RUNNING` | `SUCCESSFUL` | `FAILED` | `SKIPPED`.
- `startTime` set when the test enters `RUNNING`; always present.
- `endTime` set when the test reaches a terminal status; **omitted** while the
  test is still `RUNNING`.

### Category and test name from the pytest nodeid

- `tests/test_limits_validation.py::test_x` → category `test_limits_validation`
  (module stem), test `test_x`.
- `tests/test_x.py::TestFoo::test_y` → category `TestFoo` (class), test `test_y`.

Rule: split the nodeid on `::`; the last segment is the test name; if a class
segment is present (≥3 segments) it is the category, otherwise the module file
stem is the category.

## Status mapping and precedence

Driven by pytest's per-phase reports (`setup`, `call`, `teardown`):

| Condition | Status |
|-----------|--------|
| test start (`pytest_runtest_logstart`) | `RUNNING` |
| `setup` phase skipped | `SKIPPED` |
| `call` phase passed | `SUCCESSFUL` |
| `call` phase skipped | `SKIPPED` |
| `call` phase failed | `FAILED` |
| `setup` or `teardown` phase failed (error) | `FAILED` |

**`FAILED` is sticky:** once a test is `FAILED`, no later report downgrades it
(e.g. a `call` that passed followed by a failing `teardown` reports `FAILED`).
Otherwise the latest reported status wins. `endTime` is (re)set on each terminal
update.

## Timestamps

- Format: ISO 8601 UTC `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` — millisecond precision,
  `Z` suffix. Implementation: `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"`.
- The clock is **injectable** into `EventRecorder` (a `now` callable returning
  the ISO string, defaulting to the UTC formatter) so unit tests are
  deterministic.

## Components

### `src/drcc_validation/paths.py` — `events_file()`

```python
def events_file() -> Path | None:
    """Realtime events file path, or None outside the prod framework.

    Generated only when GENERIC_TESTS_WORKSPACE_DIR is set; the Validation
    Service monitors this exact path.
    """
    workspace = os.environ.get("GENERIC_TESTS_WORKSPACE_DIR")
    if not workspace:
        return None
    return Path(workspace) / "tests-events.json"
```

### `src/drcc_validation/runtime_events.py` — `EventRecorder` (new, pytest-agnostic)

- `__init__(self, path, now=_utc_now_iso)` — target `Path`, injectable clock.
- `set_running(nodeid)` — status `RUNNING`, `startTime = now()`, writes file.
- `set_outcome(nodeid, status)` — terminal status (respecting sticky-`FAILED`),
  `endTime = now()` (sets `startTime` too if somehow absent), writes file.
- `to_dict()` — pure builder of the schema above (testable without I/O).
- Internal state: `OrderedDict[category] -> OrderedDict[testName] -> event`.
- `_write()` — **atomic**: write to a temp file in the same directory then
  `os.replace(tmp, path)`, so the monitor never reads a partial file. Creates
  the parent directory if missing.

### `tests/conftest.py` — thin hooks

```python
from drcc_validation.paths import events_file
from drcc_validation.runtime_events import EventRecorder

_events_path = events_file()
_recorder = EventRecorder(_events_path) if _events_path else None

def pytest_runtest_logstart(nodeid, location):
    if _recorder:
        _record_safely(_recorder.set_running, nodeid)

def pytest_runtest_logreport(report):
    if _recorder:
        # map report.when / report.outcome to a status, then set_outcome
        ...
```

## Error handling

Event writing must never break the run — the tests are the deliverable. The
conftest hook wrappers swallow and log any exception from the recorder (a
`_record_safely` helper). The recorder's `_write` is defensive about missing
directories.

## Testing

Unit tests (`tests/test_runtime_events.py`) drive `EventRecorder` directly with
a `tmp_path` and a fake clock — no nested pytest:

- nodeid parsing: module-stem category; class category.
- `set_running` then `set_outcome` produce the correct schema via `to_dict()`.
- `startTime` present on RUNNING with no `endTime`; both present after terminal.
- Sticky `FAILED`: `SUCCESSFUL` (call) then `FAILED` (teardown) → `FAILED`.
- Multiple categories preserved in discovery order.
- `_write` produces a file that re-parses as valid JSON matching `to_dict()`.
- Timestamp format matches `yyyy-MM-ddTHH:mm:ss.SSSZ`.

Path tests (`tests/test_paths.py`):
- `events_file()` returns `None` when `GENERIC_TESTS_WORKSPACE_DIR` unset/empty.
- returns `<workspace>/tests-events.json` when set.

## Out of scope (YAGNI)

- No "minimal" event mode, no properties-file format (JSON only).
- No top-level or per-category timestamps (per-test-event only).
- No change to report generation, auth, or validation logic.
- No nested-pytest integration test for the hooks (recorder is tested directly;
  the hooks are thin and exercised live in prod).
