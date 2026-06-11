import textwrap
from drcc_validation.config import Contact, ReportConfig, load_report_config

def _write(tmp_path, body):
    p = tmp_path / "report_config.yaml"
    p.write_text(textwrap.dedent(body))
    return p

YAML = """
customer_name: "Acme Corp"
region_label: ""
ga_target_date: "May 8, 2026"
validation_run_date: ""
jira_url: "https://jira.example.com"
strict: false
contacts:
  - name: "Jane Doe"
    role: "Operator"
    email: "jane@example.com"
"""

def test_loads_fields_and_contacts(tmp_path):
    cfg = load_report_config(_write(tmp_path, YAML), region_default="us-ashburn-1")
    assert isinstance(cfg, ReportConfig)
    assert cfg.customer_name == "Acme Corp"
    assert cfg.region_label == "us-ashburn-1"   # blank falls back to default
    assert cfg.ga_target_date == "May 8, 2026"
    assert cfg.contacts == [Contact("Jane Doe", "Operator", "jane@example.com")]
    assert cfg.strict is False

def test_env_overrides_win(tmp_path, monkeypatch):
    monkeypatch.setenv("REPORT_CUSTOMER_NAME", "Override Inc")
    monkeypatch.setenv("REPORT_STRICT", "true")
    monkeypatch.setenv("REPORT_REGION_LABEL", "us-phoenix-1")
    cfg = load_report_config(_write(tmp_path, YAML), region_default="us-ashburn-1")
    assert cfg.customer_name == "Override Inc"
    assert cfg.strict is True
    assert cfg.region_label == "us-phoenix-1"

def test_validation_run_date_filled_when_blank(tmp_path):
    cfg = load_report_config(_write(tmp_path, YAML), run_date="June 10, 2026")
    assert cfg.validation_run_date == "June 10, 2026"

def test_empty_env_falls_back_to_yaml(tmp_path, monkeypatch):
    """Empty-string env var must not win over the YAML value."""
    monkeypatch.setenv("REPORT_CUSTOMER_NAME", "")
    cfg = load_report_config(_write(tmp_path, YAML))
    assert cfg.customer_name == "Acme Corp"
