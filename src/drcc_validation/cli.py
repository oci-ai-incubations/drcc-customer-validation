"""Orchestrate: authenticate → query limits → validate → render reports."""
from __future__ import annotations

import argparse
import datetime
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
    run_date = datetime.date.today().strftime("%B %d, %Y")
    cfg = load_report_config(config_path, region_default=ctx.region, run_date=run_date)
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
