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
