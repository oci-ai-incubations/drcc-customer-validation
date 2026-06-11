# DRCC Service Limits Validation & Reporting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate an OCI region's configured service limits against `manifest/Default_Limits.xlsx` and produce a DRCC Region Readiness report (HTML + PDF) and a detailed Validation Limits report (PDF), runnable as a containerized pytest suite.

**Architecture:** A small Python package (`src/drcc_validation/`) with pure-logic modules (manifest parsing, comparison) that are fully unit-tested without cloud access, plus an OCI-facing layer (auth, limits client) and Jinja2/WeasyPrint report renderers. `OCI_ENV` selects config-file auth (`dev`) or resource-principal auth (`prod`). pytest is the entrypoint; the live integration test always emits both reports then asserts no errors when strict.

**Tech Stack:** Python 3.12, `oci`, `openpyxl`, `pyyaml`, `jinja2`, `weasyprint`, `matplotlib`, `pytest`; Docker (`python:3.12-slim`).

**Spec:** `docs/superpowers/specs/2026-06-10-drcc-limits-validation-design.md`

---

## Status semantics (used throughout)

From the HTML template legend:
- `actual == expected` → **Pass**
- `actual < expected` → **Error** (lower than contracted)
- `actual > expected` → **Warning** (higher than manifest)
- no live value for a manifest limit → **Incomplete**

**Scope:** all limits are scoped to global — the per-AD/region values OCI returns
for a `(service, limit)` are **summed into one region total** and compared once,
so there is exactly one check per manifest row (recorded with
`scope_type = "GLOBAL"`). (Superseded the original per-AD-expansion design at the
user's request after the first live run.)

---

## Task 0: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `.dockerignore`
- Create: `src/drcc_validation/__init__.py`
- Create: `config/report_config.yaml`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
oci==2.178.0
openpyxl==3.1.5
pyyaml==6.0.2
jinja2==3.1.4
weasyprint==69.0
pydyf==0.12.1
matplotlib==3.10.9
pytest==8.3.3
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
markers =
    integration: live test that calls OCI and emits reports
addopts = -ra
```

- [ ] **Step 3: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
output/
.pytest_cache/
```

- [ ] **Step 4: Create `.dockerignore`**

```
.venv/
__pycache__/
output/
.git/
docs/
*.pyc
```

- [ ] **Step 5: Create empty `src/drcc_validation/__init__.py` and `tests/__init__.py`**

Both files contain a single comment line: `# package marker`

- [ ] **Step 6: Create `config/report_config.yaml`**

```yaml
customer_name: "Example Customer"
region_label: ""          # blank → auto-filled from detected OCI region
ga_target_date: "TBD"
validation_run_date: ""   # blank → filled by CLI at run time
jira_url: "https://jira.oraclecloud.com/secure/CreateIssue.jspa"
strict: false             # true → pytest fails the build when errors > 0
contacts:
  - name: "Primary Contact"
    role: "OCI Region Operator · Primary Contact"
    email: "primary.contact@example.com"
  - name: "Secondary Contact"
    role: "OCI Region Operator · Secondary Contact"
    email: "secondary.contact@example.com"
```

- [ ] **Step 7: Create local dev venv and install deps**

Run:
```bash
python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -r requirements.txt
```
Expected: installs without error. (WeasyPrint needs system libs; on macOS `brew install pango gdk-pixbuf libffi` if import fails. Docker handles this for the real run.)

- [ ] **Step 8: Initialize git and commit**

Run:
```bash
git init && git add -A && git commit -m "chore: scaffold DRCC limits validation project"
```

---

## Task 1: Manifest parser (`manifest.py`)

**Files:**
- Create: `src/drcc_validation/manifest.py`
- Test: `tests/test_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_manifest.py
from pathlib import Path
from drcc_validation.manifest import ManifestLimit, load_manifest

MANIFEST = Path(__file__).resolve().parents[1] / "manifest" / "Default_Limits.xlsx"

def test_load_manifest_returns_all_rows():
    limits = load_manifest(MANIFEST)
    assert len(limits) == 612

def test_first_row_parsed_correctly():
    limits = load_manifest(MANIFEST)
    first = limits[0]
    assert isinstance(first, ManifestLimit)
    assert first.service == "big-data"
    assert first.limit == "bm-optimized3-36-memory-gb-size"
    assert first.description == "BM.Optimized3.36 - Total Memory in GBs"
    assert first.is_spending_limit is False
    assert first.is_managed_by_operator is True
    assert first.expected_value == 0

def test_unique_service_count():
    limits = load_manifest(MANIFEST)
    assert len({l.service for l in limits}) == 82
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_manifest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drcc_validation'` or import error. (Run pytest from repo root; `pytest.ini` + package layout under `src` requires `PYTHONPATH=src` — set it: `PYTHONPATH=src .venv/bin/pytest ...`.)

- [ ] **Step 3: Write minimal implementation**

```python
# src/drcc_validation/manifest.py
"""Parse the Default_Limits manifest spreadsheet into typed records."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl


@dataclass(frozen=True)
class ManifestLimit:
    service: str
    limit: str
    description: str
    is_spending_limit: bool
    is_managed_by_operator: bool
    expected_value: int


def load_manifest(path: str | Path) -> list[ManifestLimit]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    limits: list[ManifestLimit] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[0] is None:
            continue
        limits.append(
            ManifestLimit(
                service=str(row[0]),
                limit=str(row[1]),
                description=str(row[2]) if row[2] is not None else "",
                is_spending_limit=bool(row[3]),
                is_managed_by_operator=bool(row[4]),
                expected_value=int(row[5]) if row[5] is not None else 0,
            )
        )
    wb.close()
    return limits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_manifest.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/manifest.py tests/test_manifest.py
git commit -m "feat: parse Default_Limits manifest into typed records"
```

---

## Task 2: Report config loader (`config.py`)

**Files:**
- Create: `src/drcc_validation/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_config.py -v`
Expected: FAIL — cannot import `drcc_validation.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/drcc_validation/config.py
"""Report metadata config: YAML file with per-field env overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Contact:
    name: str
    role: str
    email: str


@dataclass
class ReportConfig:
    customer_name: str
    region_label: str
    ga_target_date: str
    validation_run_date: str
    jira_url: str
    strict: bool
    contacts: list[Contact] = field(default_factory=list)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_report_config(
    path: str | Path,
    region_default: str | None = None,
    run_date: str | None = None,
) -> ReportConfig:
    data = yaml.safe_load(Path(path).read_text()) or {}

    def pick(key: str, env: str, default: str = "") -> str:
        return os.environ.get(env, data.get(key) or default)

    region_label = pick("region_label", "REPORT_REGION_LABEL")
    if not region_label and region_default:
        region_label = region_default

    run_date_value = pick("validation_run_date", "REPORT_VALIDATION_RUN_DATE")
    if not run_date_value and run_date:
        run_date_value = run_date

    strict = data.get("strict", False)
    if "REPORT_STRICT" in os.environ:
        strict = _as_bool(os.environ["REPORT_STRICT"])

    contacts = [
        Contact(c["name"], c.get("role", ""), c.get("email", ""))
        for c in (data.get("contacts") or [])
    ]

    return ReportConfig(
        customer_name=pick("customer_name", "REPORT_CUSTOMER_NAME"),
        region_label=region_label,
        ga_target_date=pick("ga_target_date", "REPORT_GA_TARGET_DATE", "TBD"),
        validation_run_date=run_date_value,
        jira_url=pick("jira_url", "REPORT_JIRA_URL"),
        strict=_as_bool(strict),
        contacts=contacts,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/config.py tests/test_config.py
git commit -m "feat: report config loader with env overrides"
```

---

## Task 3: Validator (`validator.py`)

**Files:**
- Create: `src/drcc_validation/validator.py`
- Test: `tests/test_validator.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validator.py
from drcc_validation.manifest import ManifestLimit
from drcc_validation.limits_client import LiveLimitValue
from drcc_validation.validator import Status, validate


def m(service, limit, expected):
    return ManifestLimit(service, limit, f"{limit} desc", False, True, expected)


def live(service, name, value, scope="REGION", ad=None):
    return LiveLimitValue(service, name, scope, ad, value)


def test_pass_when_equal():
    summary = validate([m("compute", "cores", 10)], [live("compute", "cores", 10)])
    assert summary.results[0].status == Status.PASS
    assert summary.passed == 1 and summary.total_checked == 1


def test_error_when_actual_lower():
    summary = validate([m("compute", "cores", 10)], [live("compute", "cores", 4)])
    assert summary.results[0].status == Status.ERROR
    assert summary.errors == 1


def test_warning_when_actual_higher():
    summary = validate([m("compute", "cores", 10)], [live("compute", "cores", 99)])
    assert summary.results[0].status == Status.WARNING
    assert summary.warnings == 1


def test_incomplete_when_no_live_value():
    summary = validate([m("vcn", "subnets", 5)], [])
    r = summary.results[0]
    assert r.status == Status.INCOMPLETE
    assert r.actual is None
    assert summary.incomplete == 1


def test_per_ad_expansion_creates_multiple_results():
    manifest = [m("compute", "cores", 10)]
    values = [
        live("compute", "cores", 10, scope="AD", ad="AD-1"),
        live("compute", "cores", 4, scope="AD", ad="AD-2"),
    ]
    summary = validate(manifest, values)
    assert summary.total_checked == 2
    assert summary.passed == 1 and summary.errors == 1


def test_per_service_summary_rollup():
    manifest = [m("compute", "a", 10), m("compute", "b", 10), m("vcn", "c", 1)]
    values = [
        live("compute", "a", 10),
        live("compute", "b", 4),
        live("vcn", "c", 1),
    ]
    summary = validate(manifest, values)
    by_service = {s.service: s for s in summary.services}
    assert by_service["compute"].checked == 2
    assert by_service["compute"].passed == 1
    assert by_service["compute"].errors == 1
    assert by_service["vcn"].passed == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_validator.py -v`
Expected: FAIL — cannot import `drcc_validation.validator` (and `limits_client` not yet created; Task 4/5 create it, but `LiveLimitValue` is needed here). Create a minimal `LiveLimitValue` stub now in Task 3 Step 3 so this test imports; Task 5 fills the rest of `limits_client.py`.

- [ ] **Step 3: Write minimal implementation**

First add the shared `LiveLimitValue` dataclass so it can be imported by both validator and (later) the client:

```python
# src/drcc_validation/limits_client.py  (initial stub — extended in Task 5)
"""Live OCI limit values."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiveLimitValue:
    service: str
    name: str
    scope_type: str            # GLOBAL | REGION | AD
    availability_domain: str | None
    value: int
```

Then the validator:

```python
# src/drcc_validation/validator.py
"""Compare manifest limits against live OCI limit values."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from .limits_client import LiveLimitValue
from .manifest import ManifestLimit


class Status(str, Enum):
    PASS = "Pass"
    ERROR = "Error"
    WARNING = "Warning"
    INCOMPLETE = "Incomplete"


@dataclass(frozen=True)
class LimitResult:
    service: str
    limit: str
    description: str
    expected: int
    actual: int | None
    scope_type: str | None
    availability_domain: str | None
    status: Status


@dataclass
class ServiceSummary:
    service: str
    checked: int = 0
    passed: int = 0
    errors: int = 0
    warnings: int = 0
    incomplete: int = 0


@dataclass
class ValidationSummary:
    results: list[LimitResult] = field(default_factory=list)
    services: list[ServiceSummary] = field(default_factory=list)
    total_checked: int = 0
    passed: int = 0
    errors: int = 0
    warnings: int = 0
    incomplete: int = 0


def _status_for(expected: int, actual: int) -> Status:
    if actual == expected:
        return Status.PASS
    if actual < expected:
        return Status.ERROR
    return Status.WARNING


def validate(
    manifest: list[ManifestLimit], live: list[LiveLimitValue]
) -> ValidationSummary:
    live_by_key: dict[tuple[str, str], list[LiveLimitValue]] = defaultdict(list)
    for v in live:
        live_by_key[(v.service, v.name)].append(v)

    results: list[LimitResult] = []
    for ml in manifest:
        matches = live_by_key.get((ml.service, ml.limit), [])
        if not matches:
            results.append(
                LimitResult(
                    ml.service, ml.limit, ml.description, ml.expected_value,
                    None, None, None, Status.INCOMPLETE,
                )
            )
            continue
        for v in matches:
            results.append(
                LimitResult(
                    ml.service, ml.limit, ml.description, ml.expected_value,
                    v.value, v.scope_type, v.availability_domain,
                    _status_for(ml.expected_value, v.value),
                )
            )

    svc_map: dict[str, ServiceSummary] = {}
    summary = ValidationSummary(results=results)
    for r in results:
        s = svc_map.setdefault(r.service, ServiceSummary(r.service))
        s.checked += 1
        summary.total_checked += 1
        if r.status == Status.PASS:
            s.passed += 1
            summary.passed += 1
        elif r.status == Status.ERROR:
            s.errors += 1
            summary.errors += 1
        elif r.status == Status.WARNING:
            s.warnings += 1
            summary.warnings += 1
        else:
            s.incomplete += 1
            summary.incomplete += 1

    summary.services = sorted(
        svc_map.values(), key=lambda s: (-s.errors, -s.warnings, s.service)
    )
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_validator.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/validator.py src/drcc_validation/limits_client.py tests/test_validator.py
git commit -m "feat: manifest-vs-live limit comparison and aggregation"
```

---

## Task 4: Auth factory (`auth.py`)

**Files:**
- Create: `src/drcc_validation/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth.py
import drcc_validation.auth as auth
from drcc_validation.auth import build_oci_context


def test_dev_uses_config_file(monkeypatch):
    fake_cfg = {"tenancy": "ocid1.tenancy.oc1..t", "region": "us-ashburn-1"}
    monkeypatch.setattr(auth.oci.config, "from_file", lambda profile_name: fake_cfg)
    monkeypatch.setenv("OCI_ENV", "dev")
    monkeypatch.setenv("OCI_PROFILE", "DEFAULT")
    ctx = build_oci_context()
    assert ctx.signer is None
    assert ctx.tenancy_id == "ocid1.tenancy.oc1..t"
    assert ctx.region == "us-ashburn-1"


def test_prod_uses_resource_principal(monkeypatch):
    class FakeSigner:
        tenancy_id = "ocid1.tenancy.oc1..rp"
        region = "us-phoenix-1"

    monkeypatch.setattr(
        auth.oci.auth.signers,
        "get_resource_principals_signer",
        lambda: FakeSigner(),
    )
    monkeypatch.setenv("OCI_ENV", "prod")
    monkeypatch.delenv("OCI_TENANCY", raising=False)
    monkeypatch.delenv("OCI_REGION", raising=False)
    ctx = build_oci_context()
    assert ctx.signer is not None
    assert ctx.tenancy_id == "ocid1.tenancy.oc1..rp"
    assert ctx.region == "us-phoenix-1"


def test_prod_env_overrides(monkeypatch):
    class FakeSigner:
        tenancy_id = "ocid1.tenancy.oc1..rp"
        region = "us-phoenix-1"

    monkeypatch.setattr(
        auth.oci.auth.signers,
        "get_resource_principals_signer",
        lambda: FakeSigner(),
    )
    monkeypatch.setenv("OCI_ENV", "prod")
    monkeypatch.setenv("OCI_TENANCY", "ocid1.tenancy.oc1..override")
    monkeypatch.setenv("OCI_REGION", "uk-london-1")
    ctx = build_oci_context()
    assert ctx.tenancy_id == "ocid1.tenancy.oc1..override"
    assert ctx.region == "uk-london-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_auth.py -v`
Expected: FAIL — cannot import `drcc_validation.auth`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/drcc_validation/auth.py
"""Build OCI auth context for dev (config file) or prod (resource principal)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import oci


@dataclass
class OciContext:
    config: dict
    signer: object | None
    tenancy_id: str
    region: str


def build_oci_context(env: str | None = None) -> OciContext:
    env = (env or os.environ.get("OCI_ENV", "dev")).strip().lower()

    if env == "prod":
        signer = oci.auth.signers.get_resource_principals_signer()
        tenancy = os.environ.get("OCI_TENANCY") or getattr(signer, "tenancy_id", "")
        region = (
            os.environ.get("OCI_REGION")
            or os.environ.get("OCI_RESOURCE_PRINCIPAL_REGION")
            or getattr(signer, "region", "")
        )
        return OciContext(config={"region": region}, signer=signer,
                          tenancy_id=tenancy, region=region)

    profile = os.environ.get("OCI_PROFILE", "DEFAULT")
    config = oci.config.from_file(profile_name=profile)
    return OciContext(
        config=config,
        signer=None,
        tenancy_id=config["tenancy"],
        region=config.get("region", ""),
    )


def build_limits_client(ctx: OciContext):
    if ctx.signer is not None:
        return oci.limits.LimitsClient(config=ctx.config, signer=ctx.signer)
    return oci.limits.LimitsClient(ctx.config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_auth.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/auth.py tests/test_auth.py
git commit -m "feat: OCI auth factory for dev config-file and prod resource-principal"
```

---

## Task 5: Live limits client (`limits_client.py`)

**Files:**
- Modify: `src/drcc_validation/limits_client.py` (extend the Task 3 stub)
- Test: `tests/test_limits_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_limits_client.py
from types import SimpleNamespace
from drcc_validation.limits_client import LiveLimitValue, fetch_live_limits


class FakeClient:
    """Stands in for oci.limits.LimitsClient; records calls."""
    def __init__(self, values_by_service):
        self.values_by_service = values_by_service
        self.calls = []

    def list_limit_values(self, compartment_id, service_name=None, **kwargs):
        self.calls.append((compartment_id, service_name))
        return service_name


def fake_pager(list_func, compartment_id, service_name=None, **kwargs):
    # mimic oci.pagination.list_call_get_all_results(...).data
    svc = list_func(compartment_id, service_name=service_name)
    items = client_values[svc]
    return SimpleNamespace(data=items)


client_values = {
    "compute": [
        SimpleNamespace(name="cores", scope_type="AD", availability_domain="AD-1", value=10),
        SimpleNamespace(name="cores", scope_type="AD", availability_domain="AD-2", value=4),
    ],
    "vcn": [
        SimpleNamespace(name="subnets", scope_type="REGION", availability_domain=None, value=5),
    ],
}


def test_fetch_live_limits_flattens_all_services(monkeypatch):
    import drcc_validation.limits_client as lc
    monkeypatch.setattr(lc.oci.pagination, "list_call_get_all_results", fake_pager)
    client = FakeClient(client_values)
    out = fetch_live_limits(client, "ocid1.tenancy.oc1..t", ["compute", "vcn"])
    assert LiveLimitValue("compute", "cores", "AD", "AD-1", 10) in out
    assert LiveLimitValue("compute", "cores", "AD", "AD-2", 4) in out
    assert LiveLimitValue("vcn", "subnets", "REGION", None, 5) in out
    assert len(out) == 3
    assert ("ocid1.tenancy.oc1..t", "compute") in client.calls


def test_fetch_skips_values_with_none_value(monkeypatch):
    import drcc_validation.limits_client as lc
    monkeypatch.setattr(lc.oci.pagination, "list_call_get_all_results", fake_pager)
    client_values["empty"] = [
        SimpleNamespace(name="x", scope_type="REGION", availability_domain=None, value=None),
    ]
    client = FakeClient(client_values)
    out = fetch_live_limits(client, "t", ["empty"])
    assert out == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_limits_client.py -v`
Expected: FAIL — `fetch_live_limits` not defined.

- [ ] **Step 3: Write minimal implementation** (append to `limits_client.py` below the dataclass)

```python
# src/drcc_validation/limits_client.py  (add imports at top + function below dataclass)
import logging

import oci

logger = logging.getLogger(__name__)


def fetch_live_limits(
    limits_client, compartment_id: str, services: list[str]
) -> list[LiveLimitValue]:
    """Query list_limit_values for each service; flatten to LiveLimitValue records."""
    out: list[LiveLimitValue] = []
    for service in services:
        try:
            resp = oci.pagination.list_call_get_all_results(
                limits_client.list_limit_values,
                compartment_id,
                service_name=service,
            )
        except oci.exceptions.ServiceError as exc:
            logger.warning("Failed to fetch limits for %s: %s", service, exc)
            continue
        for item in resp.data:
            if getattr(item, "value", None) is None:
                continue
            out.append(
                LiveLimitValue(
                    service=service,
                    name=item.name,
                    scope_type=item.scope_type,
                    availability_domain=item.availability_domain,
                    value=int(item.value),
                )
            )
    return out


def unique_services(manifest_limits) -> list[str]:
    seen: dict[str, None] = {}
    for ml in manifest_limits:
        seen.setdefault(ml.service, None)
    return list(seen)
```

Note: keep the `from __future__ import annotations` and `from dataclasses import dataclass` + `LiveLimitValue` from the Task 3 stub at the top of the file; add `import logging` / `import oci` near them.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_limits_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/limits_client.py tests/test_limits_client.py
git commit -m "feat: fetch live OCI limit values per service with pagination"
```

---

## Task 6: Shared report styling + chart helpers

**Files:**
- Create: `src/drcc_validation/reports/__init__.py`
- Create: `src/drcc_validation/reports/templates/styles.css`
- Create: `src/drcc_validation/reports/charts.py`
- Test: `tests/test_charts.py`

- [ ] **Step 1: Create `src/drcc_validation/reports/__init__.py`**

Single comment line: `# reports package`

- [ ] **Step 2: Create `styles.css` by copying the existing template's CSS**

Copy the entire contents of the `<style>...</style>` block from
`/Users/jolettacheung/Downloads/DRCC-Region-Readiness-Report-Templates.html`
(lines 293–393, i.e. everything between `<style>` and `</style>`, exclusive)
into `src/drcc_validation/reports/templates/styles.css`. This is the exact CSS
used by the Jinja2 templates so the generated reports match the approved look.

- [ ] **Step 3: Write the failing test for charts**

```python
# tests/test_charts.py
from drcc_validation.reports.charts import doughnut_data_uri, bar_data_uri


def test_doughnut_returns_png_data_uri():
    uri = doughnut_data_uri(passed=10, errors=2, warnings=1, incomplete=5)
    assert uri.startswith("data:image/png;base64,")
    assert len(uri) > 200


def test_bar_returns_png_data_uri():
    uri = bar_data_uri(
        labels=["compute", "database"],
        errors=[3, 1],
        warnings=[0, 2],
    )
    assert uri.startswith("data:image/png;base64,")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_charts.py -v`
Expected: FAIL — cannot import `drcc_validation.reports.charts`.

- [ ] **Step 5: Write minimal implementation**

```python
# src/drcc_validation/reports/charts.py
"""Render summary charts to base64 PNG data URIs for embedding in HTML/PDF."""
from __future__ import annotations

import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_COLORS = {"pass": "#1e7e34", "error": "#c62828", "warning": "#e65100", "inc": "#cccccc"}


def _fig_to_data_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight", transparent=True)
    plt.close(fig)
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def doughnut_data_uri(passed: int, errors: int, warnings: int, incomplete: int) -> str:
    fig, ax = plt.subplots(figsize=(3.2, 3.2))
    data = [passed, errors, warnings, incomplete]
    labels = ["Pass", "Error", "Warning", "Incomplete"]
    colors = [_COLORS["pass"], _COLORS["error"], _COLORS["warning"], _COLORS["inc"]]
    plotted = [(d, l, c) for d, l, c in zip(data, labels, colors) if d > 0]
    if not plotted:
        plotted = [(1, "No data", "#cccccc")]
    vals, labs, cols = zip(*plotted)
    ax.pie(vals, labels=labs, colors=cols, wedgeprops={"width": 0.35},
           textprops={"fontsize": 8})
    ax.set_aspect("equal")
    return _fig_to_data_uri(fig)


def bar_data_uri(labels: list[str], errors: list[int], warnings: list[int]) -> str:
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    x = range(len(labels))
    ax.bar(x, errors, label="Errors", color=_COLORS["error"])
    ax.bar(x, warnings, bottom=errors, label="Warnings", color=_COLORS["warning"])
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    ax.tick_params(axis="y", labelsize=8)
    ax.legend(fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return _fig_to_data_uri(fig)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_charts.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add src/drcc_validation/reports/ tests/test_charts.py
git commit -m "feat: shared report CSS and matplotlib chart data-uri helpers"
```

---

## Task 7: Readiness report renderer (`reports/readiness.py`)

**Files:**
- Create: `src/drcc_validation/reports/templates/readiness.html.j2`
- Create: `src/drcc_validation/reports/templates/readiness_pdf.html.j2`
- Create: `src/drcc_validation/reports/readiness.py`
- Test: `tests/test_readiness.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_readiness.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_readiness.py -v`
Expected: FAIL — cannot import `drcc_validation.reports.readiness`.

- [ ] **Step 3: Create `readiness.html.j2`** (interactive, Chart.js — mirrors the 4-view approved template, data-driven)

```jinja
<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DRCC Region Readiness Report — {{ cfg.customer_name }}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>{{ css }}</style>
</head><body id="artifacts-component-root-html">
<div class="nav">
  <button class="nav-btn active" onclick="show(0)">1 · Executive</button>
  <button class="nav-btn" onclick="show(1)">2 · Scorecard</button>
  <button class="nav-btn" onclick="show(2)">3 · Detailed + Charts</button>
  <button class="nav-btn" onclick="show(3)">4 · Certificate</button>
</div>

{% set badge = 'badge-pass' if s.errors == 0 else 'badge-warn' %}
{% set verdict_cls = 'verdict-pass' if s.errors == 0 else 'verdict-warn' %}
{% set status_text = '✓ Ready for GA' if s.errors == 0 else '⚠ Attention Required' %}

<!-- TEMPLATE 1 — Executive -->
<div class="template active" id="t0">
  <div class="report-card">
    <div class="report-header">
      <div>
        <div class="oracle-logo">ORACLE CLOUD INFRASTRUCTURE</div>
        <div class="report-title" style="margin-top:6px;">Region Readiness Report</div>
        <div class="report-sub">{{ cfg.customer_name }} · {{ cfg.region_label }}</div>
        <div class="report-sub">Validation run: {{ cfg.validation_run_date }} · Prepared by Oracle Cloud</div>
      </div>
      <span class="badge {{ badge }}" style="font-size:12px;padding:5px 14px;margin-top:4px;">{{ status_text }}</span>
    </div>
    <div class="verdict {{ verdict_cls }}">
      Service limit validation for your region is complete.
      {% if s.errors or s.warnings %}
      <strong>{{ s.errors }} errors</strong> and <strong>{{ s.warnings }} warnings</strong> were identified that require resolution before your region can be confirmed as production-ready.
      {% else %}
      All checked limits match the approved manifest.
      {% endif %}
    </div>
    <div class="metric-row">
      <div class="metric"><div class="ml">Limits validated</div><div class="mv" style="color:#1a1a1a;">{{ s.total_checked }}</div></div>
      <div class="metric"><div class="ml">✓ Passed</div><div class="mv c-pass">{{ s.passed }}</div></div>
      <div class="metric"><div class="ml">✗ Errors</div><div class="mv c-err">{{ s.errors }}</div></div>
      <div class="metric"><div class="ml">⚠ Warnings</div><div class="mv c-warn">{{ s.warnings }}</div></div>
    </div>
    <hr class="divider">
    <div class="section-label">Contact &amp; support</div>
    {% for c in cfg.contacts %}
    <div class="contact-row">
      <div class="contact-avatar">{{ c.name.split()|map('first')|join|upper }}</div>
      <div><div class="contact-name">{{ c.name }}</div><div class="contact-role">{{ c.role }}</div></div>
      <a href="mailto:{{ c.email }}" class="contact-link">Email</a>
    </div>
    {% endfor %}
    <div style="margin-top:12px;"><a class="jira-btn" href="{{ cfg.jira_url }}" target="_blank">+ Create JIRA Ticket</a></div>
    <div class="footer-note" style="margin-top:1.5rem;">Generated by the Oracle DRCC Validation Agent · Confidential · For customer use only</div>
  </div>
</div>

<!-- TEMPLATE 2 — Scorecard -->
<div class="template" id="t1">
  <div class="report-card">
    <div class="report-header">
      <div>
        <div class="oracle-logo">ORACLE CLOUD INFRASTRUCTURE</div>
        <div class="report-title" style="margin-top:6px;">Region Readiness Report — Service Scorecard</div>
        <div class="report-sub">{{ cfg.customer_name }} · {{ cfg.region_label }} · {{ cfg.validation_run_date }}</div>
      </div>
      <span class="badge {{ badge }}" style="font-size:12px;padding:5px 14px;">{{ status_text }}</span>
    </div>
    <div class="meta-grid">
      <div class="meta-cell"><div class="meta-key">Customer</div><div class="meta-val">{{ cfg.customer_name }}</div></div>
      <div class="meta-cell"><div class="meta-key">Region</div><div class="meta-val">{{ cfg.region_label }}</div></div>
      <div class="meta-cell"><div class="meta-key">GA Target Date</div><div class="meta-val">{{ cfg.ga_target_date }}</div></div>
      <div class="meta-cell"><div class="meta-key">Services Checked</div><div class="meta-val">{{ s.services|length }}</div></div>
    </div>
    <div class="section-label">Per-service results</div>
    <table class="svc-table">
      <thead><tr><th>Service</th><th>Status</th><th>Checked</th><th>Pass</th><th>Errors</th><th>Warnings</th></tr></thead>
      <tbody>
      {% for svc in s.services %}
        {% set sb = 'badge-pass' if (svc.errors==0 and svc.warnings==0 and svc.incomplete==0) else ('badge-err' if svc.errors else ('badge-warn' if svc.warnings else 'badge-inc')) %}
        {% set st = 'Pass' if (svc.errors==0 and svc.warnings==0 and svc.incomplete==0) else ('Error' if svc.errors else ('Warning' if svc.warnings else 'Incomplete')) %}
        <tr><td>{{ svc.service }}</td><td><span class="badge {{ sb }}">{{ st }}</span></td><td>{{ svc.checked }}</td><td>{{ svc.passed }}</td><td>{{ svc.errors }}</td><td>{{ svc.warnings }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    <div class="footer-note">Oracle DRCC Validation Agent · Confidential · For customer use only</div>
  </div>
</div>

<!-- TEMPLATE 3 — Detailed + Charts -->
<div class="template" id="t2">
  <div class="report-card">
    <div class="report-header">
      <div>
        <div class="oracle-logo">ORACLE CLOUD INFRASTRUCTURE</div>
        <div class="report-title" style="margin-top:6px;">Region Readiness Report — Detailed</div>
        <div class="report-sub">{{ cfg.customer_name }} · {{ cfg.region_label }} · {{ cfg.validation_run_date }}</div>
      </div>
      <span class="badge {{ badge }}" style="font-size:12px;padding:5px 14px;">{{ status_text }}</span>
    </div>
    <div class="chart-grid">
      <div><div class="section-label">Results overview</div><div class="chart-wrap" style="height:220px;"><canvas id="doughnutChart"></canvas></div></div>
      <div><div class="section-label">Top services by error count</div><div class="chart-wrap" style="height:220px;"><canvas id="barChart"></canvas></div></div>
    </div>
    <div class="section-label">What each status means</div>
    <div style="font-size:13px;line-height:1.8;margin-bottom:1.25rem;">
      <div><span class="badge badge-pass" style="margin-right:8px;">Pass</span>Limit matches the approved manifest.</div>
      <div><span class="badge badge-err" style="margin-right:8px;">Error</span>Limit is lower than contracted.</div>
      <div><span class="badge badge-warn" style="margin-right:8px;">Warning</span>Limit is higher than the manifest.</div>
      <div><span class="badge badge-inc" style="margin-right:8px;">Incomplete</span>Live data not available.</div>
    </div>
    <div class="footer-note">Oracle DRCC Validation Agent · Confidential · For customer use only</div>
  </div>
</div>

<!-- TEMPLATE 4 — Certificate -->
<div class="template" id="t3">
  <div class="report-card">
    <div style="text-align:center;padding:1.5rem 0 1rem;">
      <div class="oracle-logo" style="margin-bottom:8px;">ORACLE CLOUD INFRASTRUCTURE</div>
      <div class="report-title">Region Readiness Report</div>
      <div class="report-sub" style="margin-top:4px;">{{ cfg.customer_name }} · {{ cfg.region_label }} · {{ cfg.validation_run_date }}</div>
    </div>
    <hr class="divider">
    <div class="pill-row">
      <div class="pill"><span class="dot dot-pass"></span><span>{{ s.passed }} limits confirmed</span></div>
      <div class="pill"><span class="dot dot-err"></span><span>{{ s.errors }} errors</span></div>
      <div class="pill"><span class="dot dot-warn"></span><span>{{ s.warnings }} warnings</span></div>
      <div class="pill"><span class="dot dot-inc"></span><span>{{ s.incomplete }} incomplete</span></div>
    </div>
    <div class="footer-note" style="margin-top:1.5rem;">Oracle DRCC Validation Agent · Confidential · For customer use only</div>
  </div>
</div>

<script>
function show(i){document.querySelectorAll('.template').forEach((t,j)=>t.classList.toggle('active',i===j));
document.querySelectorAll('.nav-btn').forEach((b,j)=>b.classList.toggle('active',i===j));
if(i===2) setTimeout(initCharts,100);}
let chartsInit=false;
function initCharts(){if(chartsInit)return;chartsInit=true;
new Chart(document.getElementById('doughnutChart'),{type:'doughnut',data:{labels:['Pass','Error','Warning','Incomplete'],datasets:[{data:[{{ s.passed }},{{ s.errors }},{{ s.warnings }},{{ s.incomplete }}],backgroundColor:['#1e7e34','#c62828','#e65100','#cccccc'],borderWidth:2,borderColor:'#fff'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},cutout:'65%'}});
new Chart(document.getElementById('barChart'),{type:'bar',data:{labels:{{ top_labels|tojson }},datasets:[{label:'Errors',data:{{ top_errors|tojson }},backgroundColor:'#c62828'},{label:'Warnings',data:{{ top_warnings|tojson }},backgroundColor:'#e65100'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom'}},scales:{x:{stacked:true},y:{stacked:true}}}});}
</script></body></html>
```

- [ ] **Step 4: Create `readiness_pdf.html.j2`** (print version — all sections stacked, charts as `<img>` data URIs, no JS)

```jinja
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{{ css }}
@page { size: A4; margin: 1.5cm; }
.template { display: block !important; page-break-after: always; max-width: none; padding: 0; }
.nav, .dl-bar { display: none; }
</style></head><body>
{% set badge = 'badge-pass' if s.errors == 0 else 'badge-warn' %}
{% set status_text = '✓ Ready for GA' if s.errors == 0 else '⚠ Attention Required' %}

<div class="template">
  <div class="report-card">
    <div class="report-header">
      <div>
        <div class="oracle-logo">ORACLE CLOUD INFRASTRUCTURE</div>
        <div class="report-title" style="margin-top:6px;">Region Readiness Report</div>
        <div class="report-sub">{{ cfg.customer_name }} · {{ cfg.region_label }} · {{ cfg.validation_run_date }}</div>
      </div>
      <span class="badge {{ badge }}">{{ status_text }}</span>
    </div>
    <div class="metric-row">
      <div class="metric"><div class="ml">Limits validated</div><div class="mv">{{ s.total_checked }}</div></div>
      <div class="metric"><div class="ml">Passed</div><div class="mv c-pass">{{ s.passed }}</div></div>
      <div class="metric"><div class="ml">Errors</div><div class="mv c-err">{{ s.errors }}</div></div>
      <div class="metric"><div class="ml">Warnings</div><div class="mv c-warn">{{ s.warnings }}</div></div>
    </div>
    <div class="chart-grid">
      <div><div class="section-label">Results overview</div><img src="{{ doughnut_uri }}" style="max-width:100%;"></div>
      <div><div class="section-label">Top services by errors</div><img src="{{ bar_uri }}" style="max-width:100%;"></div>
    </div>
    <div class="meta-grid">
      <div class="meta-cell"><div class="meta-key">Customer</div><div class="meta-val">{{ cfg.customer_name }}</div></div>
      <div class="meta-cell"><div class="meta-key">Region</div><div class="meta-val">{{ cfg.region_label }}</div></div>
      <div class="meta-cell"><div class="meta-key">GA Target</div><div class="meta-val">{{ cfg.ga_target_date }}</div></div>
      <div class="meta-cell"><div class="meta-key">Services Checked</div><div class="meta-val">{{ s.services|length }}</div></div>
    </div>
  </div>
</div>

<div class="template">
  <div class="report-card">
    <div class="section-label">Per-service results</div>
    <table class="svc-table">
      <thead><tr><th>Service</th><th>Status</th><th>Checked</th><th>Pass</th><th>Errors</th><th>Warnings</th></tr></thead>
      <tbody>
      {% for svc in s.services %}
        {% set sb = 'badge-pass' if (svc.errors==0 and svc.warnings==0 and svc.incomplete==0) else ('badge-err' if svc.errors else ('badge-warn' if svc.warnings else 'badge-inc')) %}
        {% set st = 'Pass' if (svc.errors==0 and svc.warnings==0 and svc.incomplete==0) else ('Error' if svc.errors else ('Warning' if svc.warnings else 'Incomplete')) %}
        <tr><td>{{ svc.service }}</td><td><span class="badge {{ sb }}">{{ st }}</span></td><td>{{ svc.checked }}</td><td>{{ svc.passed }}</td><td>{{ svc.errors }}</td><td>{{ svc.warnings }}</td></tr>
      {% endfor %}
      </tbody>
    </table>
    <div class="section-label" style="margin-top:1.5rem;">Your Oracle contacts</div>
    {% for c in cfg.contacts %}
    <div class="contact-row"><div><div class="contact-name">{{ c.name }}</div><div class="contact-role">{{ c.role }} · {{ c.email }}</div></div></div>
    {% endfor %}
    <div class="footer-note" style="margin-top:1.5rem;">Oracle DRCC Validation Agent · Confidential · For customer use only</div>
  </div>
</div>
</body></html>
```

- [ ] **Step 5: Write `readiness.py`**

```python
# src/drcc_validation/reports/readiness.py
"""Render the DRCC Region Readiness report as HTML and PDF."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from ..config import ReportConfig
from ..validator import ValidationSummary
from .charts import bar_data_uri, doughnut_data_uri

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)


def _css() -> str:
    return (_TEMPLATE_DIR / "styles.css").read_text()


def _top_services(summary: ValidationSummary, n: int = 6):
    ranked = [s for s in summary.services if s.errors or s.warnings][:n]
    return (
        [s.service for s in ranked],
        [s.errors for s in ranked],
        [s.warnings for s in ranked],
    )


def render_readiness_html(
    summary: ValidationSummary, cfg: ReportConfig, out_path: str | Path
) -> Path:
    labels, errs, warns = _top_services(summary)
    html = _env.get_template("readiness.html.j2").render(
        s=summary, cfg=cfg, css=_css(),
        top_labels=labels, top_errors=errs, top_warnings=warns,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out


def render_readiness_pdf(
    summary: ValidationSummary, cfg: ReportConfig, out_path: str | Path
) -> Path:
    labels, errs, warns = _top_services(summary)
    html = _env.get_template("readiness_pdf.html.j2").render(
        s=summary, cfg=cfg, css=_css(),
        doughnut_uri=doughnut_data_uri(
            summary.passed, summary.errors, summary.warnings, summary.incomplete
        ),
        bar_uri=bar_data_uri(labels, errs, warns),
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out))
    return out
```

- [ ] **Step 6: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_readiness.py -v`
Expected: 2 passed. (If WeasyPrint raises an OSError about missing libs locally, install them per Task 0 Step 7; the test still validates HTML even if PDF is skipped — but aim to run it in Docker where libs are present.)

- [ ] **Step 7: Commit**

```bash
git add src/drcc_validation/reports/ tests/test_readiness.py
git commit -m "feat: render Region Readiness report as HTML and PDF"
```

---

## Task 8: Limits report renderer (`reports/limits_report.py`)

**Files:**
- Create: `src/drcc_validation/reports/templates/limits_report.html.j2`
- Create: `src/drcc_validation/reports/limits_report.py`
- Test: `tests/test_limits_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_limits_report.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_limits_report.py -v`
Expected: FAIL — cannot import `render_limits_pdf`.

- [ ] **Step 3: Create `limits_report.html.j2`**

```jinja
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{{ css }}
@page { size: A4 landscape; margin: 1.2cm; }
.report-card { page-break-inside: auto; }
table { page-break-inside: auto; }
tr { page-break-inside: avoid; }
h2.svc { font-size: 15px; margin: 1.2rem 0 0.5rem; color: #1a1a1a; }
</style></head><body>
<div class="report-card">
  <div class="oracle-logo">ORACLE CLOUD INFRASTRUCTURE</div>
  <div class="report-title" style="margin-top:6px;">Validation Limits Report</div>
  <div class="report-sub">{{ cfg.customer_name }} · {{ cfg.region_label }} · {{ cfg.validation_run_date }}</div>
  <div class="metric-row" style="margin-top:1rem;">
    <div class="metric"><div class="ml">Checked</div><div class="mv">{{ s.total_checked }}</div></div>
    <div class="metric"><div class="ml">Pass</div><div class="mv c-pass">{{ s.passed }}</div></div>
    <div class="metric"><div class="ml">Error</div><div class="mv c-err">{{ s.errors }}</div></div>
    <div class="metric"><div class="ml">Warning / Incomplete</div><div class="mv c-warn">{{ s.warnings }} / {{ s.incomplete }}</div></div>
  </div>
</div>

{% for service, rows in grouped %}
<h2 class="svc">{{ service }} <span style="font-size:11px;color:#999;">({{ rows|length }} checks)</span></h2>
<table class="svc-table">
  <thead><tr><th>Limit</th><th>Description</th><th>Expected</th><th>Actual</th><th>Scope</th><th>AD</th><th>Status</th></tr></thead>
  <tbody>
  {% for r in rows %}
    {% set sb = {'Pass':'badge-pass','Error':'badge-err','Warning':'badge-warn','Incomplete':'badge-inc'}[r.status.value] %}
    <tr>
      <td>{{ r.limit }}</td><td>{{ r.description }}</td>
      <td>{{ r.expected }}</td><td>{{ r.actual if r.actual is not none else '—' }}</td>
      <td>{{ r.scope_type or '—' }}</td><td>{{ r.availability_domain or '—' }}</td>
      <td><span class="badge {{ sb }}">{{ r.status.value }}</span></td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endfor %}
<div class="footer-note" style="margin-top:1.5rem;">Oracle DRCC Validation Agent · Confidential · For customer use only</div>
</body></html>
```

- [ ] **Step 4: Write `limits_report.py`**

```python
# src/drcc_validation/reports/limits_report.py
"""Render the detailed Validation Limits report as PDF."""
from __future__ import annotations

from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from ..config import ReportConfig
from ..validator import ValidationSummary

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)


def render_limits_pdf(
    summary: ValidationSummary, cfg: ReportConfig, out_path: str | Path
) -> Path:
    rows = sorted(summary.results, key=lambda r: (r.service, r.limit))
    grouped = [(svc, list(items)) for svc, items in groupby(rows, key=lambda r: r.service)]
    html = _env.get_template("limits_report.html.j2").render(
        s=summary, cfg=cfg, css=(_TEMPLATE_DIR / "styles.css").read_text(),
        grouped=grouped,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out))
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_limits_report.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/drcc_validation/reports/ tests/test_limits_report.py
git commit -m "feat: render detailed Validation Limits report as PDF"
```

---

## Task 9: CLI orchestration (`cli.py`)

**Files:**
- Create: `src/drcc_validation/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from drcc_validation.manifest import ManifestLimit
from drcc_validation.limits_client import LiveLimitValue
from drcc_validation.config import ReportConfig
import drcc_validation.cli as cli


def test_run_validation_produces_reports(tmp_path, monkeypatch):
    manifest = [ManifestLimit("compute", "cores", "Cores", False, True, 10)]
    live = [LiveLimitValue("compute", "cores", "REGION", None, 4)]
    cfg = ReportConfig("Acme", "us-ashburn-1", "May 8", "June 10", "http://j", False, [])

    monkeypatch.setattr(cli, "load_manifest", lambda p: manifest)
    monkeypatch.setattr(cli, "load_report_config", lambda *a, **k: cfg)

    class Ctx:
        config = {}; signer = None; tenancy_id = "ocid1.tenancy..t"; region = "us-ashburn-1"
    monkeypatch.setattr(cli, "build_oci_context", lambda: Ctx())
    monkeypatch.setattr(cli, "build_limits_client", lambda ctx: object())
    monkeypatch.setattr(cli, "fetch_live_limits", lambda c, t, svcs: live)

    summary = cli.run_validation(output_dir=tmp_path, manifest_path="x", config_path="y")

    assert summary.errors == 1
    assert (tmp_path / "DRCC-Region-Readiness-Report.html").exists()
    assert (tmp_path / "DRCC-Region-Readiness-Report.pdf").exists()
    assert (tmp_path / "Validation-Limits-Report.pdf").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py -v`
Expected: FAIL — cannot import `drcc_validation.cli`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/drcc_validation/cli.py
"""Orchestrate: authenticate → query limits → validate → render reports."""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from .auth import build_limits_client, build_oci_context
from .config import load_report_config
from .limits_client import fetch_live_limits, unique_services
from .manifest import load_manifest
from .reports.limits_report import render_limits_pdf
from .reports.readiness import render_readiness_html, render_readiness_pdf
from .validator import ValidationSummary, validate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("drcc_validation")

DEFAULT_MANIFEST = "manifest/Default_Limits.xlsx"
DEFAULT_CONFIG = "config/report_config.yaml"


def run_validation(
    output_dir, manifest_path=DEFAULT_MANIFEST, config_path=DEFAULT_CONFIG
) -> ValidationSummary:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    ctx = build_oci_context()
    logger.info("Auth ready: tenancy=%s region=%s", ctx.tenancy_id, ctx.region)

    manifest = load_manifest(manifest_path)
    cfg = load_report_config(config_path, region_default=ctx.region)
    logger.info("Loaded %d manifest limits across %d services",
                len(manifest), len(unique_services(manifest)))

    client = build_limits_client(ctx)
    live = fetch_live_limits(client, ctx.tenancy_id, unique_services(manifest))
    logger.info("Fetched %d live limit values", len(live))

    summary = validate(manifest, live)
    logger.info("Validation: %d checked, %d pass, %d error, %d warn, %d incomplete",
                summary.total_checked, summary.passed, summary.errors,
                summary.warnings, summary.incomplete)

    render_readiness_html(summary, cfg, output_dir / "DRCC-Region-Readiness-Report.html")
    render_readiness_pdf(summary, cfg, output_dir / "DRCC-Region-Readiness-Report.pdf")
    render_limits_pdf(summary, cfg, output_dir / "Validation-Limits-Report.pdf")
    logger.info("Reports written to %s", output_dir)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="DRCC service limits validation")
    parser.add_argument("--output", default=os.environ.get("OUTPUT_DIR", "output"))
    parser.add_argument("--manifest", default=os.environ.get("MANIFEST_PATH", DEFAULT_MANIFEST))
    parser.add_argument("--config", default=os.environ.get("CONFIG_PATH", DEFAULT_CONFIG))
    args = parser.parse_args()
    summary = run_validation(args.output, args.manifest, args.config)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/drcc_validation/cli.py tests/test_cli.py
git commit -m "feat: CLI orchestration tying auth, validation, and reports together"
```

---

## Task 10: Live integration test (`tests/test_limits_validation.py`)

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_limits_validation.py`

- [ ] **Step 1: Create `tests/conftest.py`** (path setup so `drcc_validation` imports without env var)

```python
# tests/conftest.py
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

- [ ] **Step 2: Write the integration test** (always emits reports, then asserts)

```python
# tests/test_limits_validation.py
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
```

- [ ] **Step 3: Run unit tests (skip integration) to confirm nothing breaks**

Run: `PYTHONPATH=src .venv/bin/pytest -m "not integration" -v`
Expected: all unit tests pass; integration tests deselected.

- [ ] **Step 4: Run the integration test against the DEFAULT profile**

Run: `OCI_ENV=dev PYTHONPATH=src .venv/bin/pytest -m integration -v`
Expected: PASS — reports appear in `output/`. (Errors won't fail the build unless `strict: true`.) Open `output/DRCC-Region-Readiness-Report.html` to eyeball it.

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_limits_validation.py
git commit -m "test: live integration test that validates limits and emits reports"
```

---

## Task 11: Dockerfile + README

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

# WeasyPrint runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libffi-dev libcairo2 shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY manifest/ ./manifest/
COPY config/ ./config/
COPY pytest.ini .
COPY tests/ ./tests/

ENV PYTHONPATH=/app/src
ENV OCI_ENV=dev
ENV OUTPUT_DIR=/app/output

# Run the full suite incl. the live integration test; emit JUnit + reports.
CMD ["pytest", "-v", "-m", "integration", "--junitxml=/app/output/results.xml"]
```

- [ ] **Step 2: Create `docker-compose.yml`** (convenience for dev runs)

```yaml
services:
  validate:
    build: .
    environment:
      OCI_ENV: ${OCI_ENV:-dev}
      OCI_PROFILE: ${OCI_PROFILE:-DEFAULT}
      REPORT_CUSTOMER_NAME: ${REPORT_CUSTOMER_NAME:-}
      REPORT_GA_TARGET_DATE: ${REPORT_GA_TARGET_DATE:-}
      REPORT_STRICT: ${REPORT_STRICT:-false}
    volumes:
      - ~/.oci:/root/.oci:ro          # dev: API-key profile (ignored in prod/RP)
      - ./output:/app/output          # reports land here
```

- [ ] **Step 3: Create `README.md`**

````markdown
# DRCC Customer Validation — Service Limits

Validates an OCI region's service limits against `manifest/Default_Limits.xlsx`
and generates a **DRCC Region Readiness report** (HTML + PDF) and a detailed
**Validation Limits report** (PDF).

## Auth modes (`OCI_ENV`)
- `dev` (default): uses `~/.oci/config` profile `OCI_PROFILE` (default `DEFAULT`).
- `prod`: uses resource-principal auth (run inside OCI with an RP-enabled
  dynamic group). Tenancy/region from the RP signer; override with
  `OCI_TENANCY` / `OCI_REGION`.

## Run locally (dev)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
OCI_ENV=dev PYTHONPATH=src .venv/bin/pytest -m integration -v
open output/DRCC-Region-Readiness-Report.html
```

## Run in Docker
```bash
# dev (mounts your ~/.oci read-only)
docker compose build
docker compose run --rm validate

# prod (resource principal; no config mount)
docker build -t drcc-validate .
docker run --rm -e OCI_ENV=prod -v "$PWD/output:/app/output" drcc-validate
```

## Report metadata
Edit `config/report_config.yaml` or override per-field with env vars
(`REPORT_CUSTOMER_NAME`, `REPORT_REGION_LABEL`, `REPORT_GA_TARGET_DATE`,
`REPORT_JIRA_URL`, `REPORT_STRICT`). Set `strict: true` to make the suite
fail the build when any limit is below the manifest.

## Status semantics
Pass = matches manifest · Error = below manifest · Warning = above manifest ·
Incomplete = no live value returned.
````

- [ ] **Step 4: Build the image**

Run: `docker build -t drcc-validate .`
Expected: builds successfully (WeasyPrint libs install, pip install completes).

- [ ] **Step 5: Run unit tests inside the container** (no OCI needed)

Run: `docker run --rm -e OCI_ENV=dev drcc-validate pytest -m "not integration" -v`
Expected: all unit tests pass.

- [ ] **Step 6: Run the full validation in Docker (dev)**

Run: `docker run --rm -e OCI_ENV=dev -v ~/.oci:/root/.oci:ro -v "$PWD/output:/app/output" drcc-validate`
Expected: integration tests run, reports written to `./output/`.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml README.md
git commit -m "feat: containerize build + run with dev/prod auth modes"
```

---

## Self-review notes

- **Spec coverage:** auth dev/prod (Task 4), manifest parse (Task 1), live query (Task 5), comparison semantics (Task 3), report metadata config+env (Task 2), Readiness HTML+PDF (Task 7), Limits PDF (Task 8), pytest entrypoint + always-emit reports (Task 10), Docker with WeasyPrint libs and OCI_ENV (Task 11). All spec sections mapped.
- **Type consistency:** `ManifestLimit`, `LiveLimitValue`, `LimitResult`, `ServiceSummary`, `ValidationSummary`, `ReportConfig`, `Contact`, `OciContext` field names are used identically across tasks. `validate()`, `fetch_live_limits()`, `unique_services()`, `build_oci_context()`, `build_limits_client()`, `load_manifest()`, `load_report_config()`, `render_readiness_html/pdf()`, `render_limits_pdf()`, `run_validation()` signatures match their call sites.
- **Ordering note:** `LiveLimitValue` is created in Task 3 (stub `limits_client.py`) because `validator.py` imports it; Task 5 extends the same file. This is called out in both tasks.
