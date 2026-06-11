from drcc_validation.manifest import ManifestLimit
from drcc_validation.limits_client import LiveLimitValue
from drcc_validation.config import ReportConfig
import drcc_validation.cli as cli


def test_run_validation_produces_reports(tmp_path, monkeypatch):
    manifest = [ManifestLimit("compute", "cores", "Cores", False, True, 10)]
    live = [LiveLimitValue("compute", "cores", "REGION", None, 4)]
    cfg = ReportConfig("Acme", "us-ashburn-1", "May 8", "June 10", "http://j", False, [])

    monkeypatch.setattr(cli, "load_manifest", lambda p: manifest)
    captured = {}
    def fake_load_config(*a, **k):
        captured.update(k)
        return cfg
    monkeypatch.setattr(cli, "load_report_config", fake_load_config)

    class Ctx:
        config = {}; signer = None; tenancy_id = "ocid1.tenancy..t"; region = "us-ashburn-1"
    monkeypatch.setattr(cli, "build_oci_context", lambda: Ctx())
    monkeypatch.setattr(cli, "build_limits_client", lambda ctx: object())
    monkeypatch.setattr(cli, "fetch_live_limits_with_status", lambda c, t, svcs: (live, {}))

    summary = cli.run_validation(output_dir=tmp_path, manifest_path="x", config_path="y")

    assert summary.errors == 1
    reports = tmp_path / "reports"
    assert (reports / "DRCC-Region-Readiness-Report.html").exists()
    assert (reports / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (reports / "Validation-Limits-Report.pdf").exists()
    assert (reports / "Validation-Limits-Report.html").exists()
    assert captured.get("run_date"), "run_date must be passed as a non-empty string"
