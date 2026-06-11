"""Render the detailed Validate Limits report (cover + TOC, aggregate page,
and one page per service) as HTML and PDF, mirroring the GitHub-style layout."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from ..validator import SEVERITY_RANK, Status, ValidationSummary

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml", "j2"]),
)

_STATUS_LABEL = {
    Status.PASS: "🟢 PASS",
    Status.WARNING: "🟡 WARNING",
    Status.ERROR: "🔴 ERROR",
    Status.INCOMPLETE: "⚪ INCOMPLETE",
    Status.MISSING: "⚪ MISSING",
}

_env.filters["statusbadge"] = lambda s: _STATUS_LABEL.get(s, str(s))
_env.filters["collstr"] = lambda pairs: ", ".join(f"{k}={v}" for k, v in pairs)


@dataclass
class RunMetadata:
    check: str
    overall_status: Status
    profile: str
    tenancy: str
    region: str
    workbooks: str
    generated: str
    services_completed: str


def overall_status(summary: ValidationSummary) -> Status:
    if summary.errors or summary.missing:
        return Status.ERROR
    if summary.warnings:
        return Status.WARNING
    if summary.query_failed:
        return Status.INCOMPLETE
    return Status.PASS


def _context(summary: ValidationSummary, meta: RunMetadata) -> dict:
    by_service = sorted(summary.services, key=lambda s: s.service)

    results_by_service: dict[str, list] = defaultdict(list)
    for r in summary.results:
        results_by_service[r.service].append(r)
    for svc, items in results_by_service.items():
        items.sort(key=lambda r: (SEVERITY_RANK[r.status], r.limit))

    # Aggregate "Findings by Service": services with any non-PASS finding,
    # grouped by overall status (Error, then Incomplete, then Warning), name.
    findings_services = sorted(
        [s for s in by_service if s.overall_status is not Status.PASS],
        key=lambda s: (SEVERITY_RANK[s.overall_status], s.service),
    )
    nonpass_by_service = {
        s.service: [r for r in results_by_service[s.service]
                    if r.status is not Status.PASS]
        for s in findings_services
    }

    return {
        "meta": meta,
        "s": summary,
        "by_service": by_service,
        "results_by_service": results_by_service,
        "findings_services": findings_services,
        "nonpass_by_service": nonpass_by_service,
        "md_files_included": 2 + len(by_service),
    }


def _render_html_string(summary: ValidationSummary, meta: RunMetadata) -> str:
    return _env.get_template("validate_limits.html.j2").render(**_context(summary, meta))


def render_validate_limits_html(
    summary: ValidationSummary, meta: RunMetadata, out_path: str | Path
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_html_string(summary, meta))
    return out


def render_validate_limits_pdf(
    summary: ValidationSummary, meta: RunMetadata, out_path: str | Path
) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=_render_html_string(summary, meta)).write_pdf(str(out))
    return out
