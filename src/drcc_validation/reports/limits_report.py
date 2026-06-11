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
