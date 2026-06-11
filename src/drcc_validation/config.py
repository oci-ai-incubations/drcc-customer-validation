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
        val = os.environ.get(env)
        if val and val.strip():
            return val
        return data.get(key) or default

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
