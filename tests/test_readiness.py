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
    # Oracle contacts are intentionally not rendered (removed from the report)
    assert "Jane Doe" not in text
    assert "jane@example.com" not in text


def test_scorecard_caps_services_at_ten(tmp_path):
    # 15 services -> the scorecard table shows only the first 10
    services = [
        ServiceSummary(f"svc-{i:02d}", checked=1, passed=0, errors=1, warnings=0, incomplete=0)
        for i in range(15)
    ]
    summary = ValidationSummary(
        results=[], services=services,
        total_checked=15, passed=0, errors=15, warnings=0, incomplete=0,
    )
    out = render_readiness_html(summary, _config(), tmp_path / "readiness.html")
    text = out.read_text()
    # Scorecard tab (#t1) is capped at 10; the Detailed tab (#t2) still lists all.
    scorecard = text.split('id="t1"', 1)[1].split('id="t2"', 1)[0]
    assert scorecard.count("<td>svc-") == 10   # 10 service rows only
    assert "<td>svc-09</td>" in scorecard and "<td>svc-10</td>" not in scorecard
    assert "<td>svc-14</td>" in text   # full list still present in the detailed view


def test_pdf_file_is_created(tmp_path):
    out = render_readiness_pdf(_summary(), _config(), tmp_path / "readiness.pdf")
    assert out.exists()
    assert out.stat().st_size > 1000
    assert out.read_bytes()[:4] == b"%PDF"
