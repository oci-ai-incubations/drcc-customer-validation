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


def test_empty_output_dir_falls_back(monkeypatch):
    monkeypatch.delenv("GENERIC_TESTS_WORKSPACE_DIR", raising=False)
    monkeypatch.setenv("OUTPUT_DIR", "")
    assert paths.artifacts_dir() == Path("output")


def test_events_file_none_when_workspace_unset(monkeypatch):
    monkeypatch.delenv("GENERIC_TESTS_WORKSPACE_DIR", raising=False)
    assert paths.events_file() is None


def test_events_file_none_when_workspace_empty(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "")
    assert paths.events_file() is None


def test_events_file_under_workspace_when_set(monkeypatch):
    monkeypatch.setenv("GENERIC_TESTS_WORKSPACE_DIR", "/workspace/job1")
    assert paths.events_file() == Path("/workspace/job1/tests-events.json")
