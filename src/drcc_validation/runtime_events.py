"""Realtime per-test event recorder for the prod Generic Tests framework.

Atomically rewrites a tests-events.json that the Validation Service monitors.
This module is pytest-agnostic so it can be unit-tested directly; the pytest
hooks in tests/conftest.py extract primitives from reports and drive it.
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict
from collections.abc import Callable
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

    when in {setup, call, teardown}; outcome in {passed, failed, skipped}.
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

    def __init__(self, path: str | os.PathLike, now: Callable[[], str] = _utc_now_iso):
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
        """Return the live (mutable) event dict for this nodeid, creating it if new.

        Callers mutate it in place; to_dict()/_ordered() copy into fresh dicts
        for output, so the stored object is never aliased externally.
        """
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
