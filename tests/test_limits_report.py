from drcc_validation.config import ReportConfig
from drcc_validation.validator import ValidationSummary, ServiceSummary, LimitResult, Status
from drcc_validation.reports.limits_report import render_limits_pdf


def _summary():
    results = [
        LimitResult("compute", "cores", "Cores", 10, 4, "AD", "AD-1", Status.ERROR),
        LimitResult("compute", "cores", "Cores", 10, 10, "AD", "AD-2", Status.PASS),
        LimitResult("vcn", "subnets", "Subnets", 5, None, None, None, Status.INCOMPLETE),
    ]
    return ValidationSummary(
        results=results,
        services=[ServiceSummary("compute", 2, 1, 1, 0, 0), ServiceSummary("vcn", 1, 0, 0, 0, 1)],
        total_checked=3, passed=1, errors=1, warnings=0, incomplete=1,
    )


def _config():
    return ReportConfig("Acme Corp", "us-ashburn-1", "May 8, 2026", "June 10, 2026",
                        "https://jira.example.com", False, [])


def test_limits_pdf_created(tmp_path):
    out = render_limits_pdf(_summary(), _config(), tmp_path / "limits.pdf")
    assert out.exists()
    assert out.read_bytes()[:4] == b"%PDF"
    assert out.stat().st_size > 1000
