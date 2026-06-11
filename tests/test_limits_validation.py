"""Live OCI integration test: validate limits and emit both reports.

Marked 'integration' — requires OCI auth (dev config profile or prod RP).
Reports are written even when assertions fail, via the always-run fixture.
"""
import os
from pathlib import Path

import pytest

from drcc_validation.cli import run_validation

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))


@pytest.fixture(scope="module")
def summary():
    return run_validation(OUTPUT_DIR)


@pytest.mark.integration
def test_reports_are_generated(summary):
    assert (OUTPUT_DIR / "DRCC-Region-Readiness-Report.html").exists()
    assert (OUTPUT_DIR / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (OUTPUT_DIR / "Validation-Limits-Report.pdf").exists()


@pytest.mark.integration
def test_some_limits_were_checked(summary):
    assert summary.total_checked > 0


@pytest.mark.integration
def test_no_limit_errors_when_strict(summary):
    from drcc_validation.config import load_report_config
    cfg = load_report_config("config/report_config.yaml")
    if not cfg.strict:
        pytest.skip("strict mode off; reporting errors without failing the build")
    assert summary.errors == 0, f"{summary.errors} limits below manifest"
