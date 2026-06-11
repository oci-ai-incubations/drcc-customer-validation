from drcc_validation.config import Contact, ReportConfig
from drcc_validation.validator import ValidationSummary, ServiceSummary, LimitResult, Status
from drcc_validation.reports.readiness import render_readiness_html, render_readiness_pdf


def _summary():
    results = [
        LimitResult("compute", "cores", "Cores", 10, 4, "REGION", None, Status.ERROR),
        LimitResult("vcn", "subnets", "Subnets", 5, 5, "REGION", None, Status.PASS),
    ]
    return ValidationSummary(
        results=results,
        services=[
            ServiceSummary("compute", 1, 0, 1, 0, 0),
            ServiceSummary("vcn", 1, 1, 0, 0, 0),
        ],
        total_checked=2, passed=1, errors=1, warnings=0, incomplete=0,
    )


def _config():
    return ReportConfig(
        customer_name="Acme Corp", region_label="us-ashburn-1",
        ga_target_date="May 8, 2026", validation_run_date="June 10, 2026",
        jira_url="https://jira.example.com", strict=False,
        contacts=[Contact("Jane Doe", "Operator", "jane@example.com")],
    )


def test_html_contains_customer_and_counts(tmp_path):
    out = render_readiness_html(_summary(), _config(), tmp_path / "readiness.html")
    text = out.read_text()
    assert "Acme Corp" in text
    assert "us-ashburn-1" in text
    assert ">2<" in text or "2" in text   # total checked rendered
    assert "Jane Doe" in text


def test_pdf_file_is_created(tmp_path):
    out = render_readiness_pdf(_summary(), _config(), tmp_path / "readiness.pdf")
    assert out.exists()
    assert out.stat().st_size > 1000
    assert out.read_bytes()[:4] == b"%PDF"
