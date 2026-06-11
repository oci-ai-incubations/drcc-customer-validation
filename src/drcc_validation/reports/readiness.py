"""Render the DRCC Region Readiness report as HTML and PDF."""
from __future__ import annotations

import datetime
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


def _generated() -> str:
    return datetime.datetime.now().strftime("%B %d, %Y %H:%M")


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
        s=summary, cfg=cfg, css=_css(), generated=_generated(),
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
        s=summary, cfg=cfg, css=_css(), generated=_generated(),
        doughnut_uri=doughnut_data_uri(
            summary.passed, summary.errors, summary.warnings, summary.incomplete
        ),
        bar_uri=bar_data_uri(labels, errs, warns),
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(out))
    return out
