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
