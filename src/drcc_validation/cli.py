"""Orchestrate: authenticate → query limits → validate → render reports."""
from __future__ import annotations

import argparse
import datetime
import logging
import os
from pathlib import Path

from .auth import build_limits_client, build_oci_context
from .config import load_report_config
from .limits_client import fetch_live_limits_with_status, unique_services
from .manifest import load_manifest
from .paths import artifacts_dir
from .reports.readiness import render_readiness_html, render_readiness_pdf
from .reports.validate_limits_report import (
    RunMetadata,
    overall_status,
    render_validate_limits_html,
    render_validate_limits_pdf,
)
from .validator import ValidationSummary, validate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("drcc_validation")

DEFAULT_MANIFEST = "manifest/Default_Limits.xlsx"
DEFAULT_CONFIG = "config/report_config.yaml"


def run_validation(
    output_dir, manifest_path=DEFAULT_MANIFEST, config_path=DEFAULT_CONFIG
) -> ValidationSummary:
    reports_dir = Path(output_dir) / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    ctx = build_oci_context()
    logger.info("Auth ready: tenancy=%s region=%s", ctx.tenancy_id, ctx.region)

    manifest = load_manifest(manifest_path)
    run_date = datetime.date.today().strftime("%B %d, %Y")
    cfg = load_report_config(config_path, region_default=ctx.region, run_date=run_date)
    services = unique_services(manifest)
    logger.info("Loaded %d manifest limits across %d services", len(manifest), len(services))

    client = build_limits_client(ctx)
    live, statuses = fetch_live_limits_with_status(client, ctx.tenancy_id, services)
    failed = {svc for svc, st in statuses.items() if not st.ok}
    logger.info("Fetched %d live limit values (%d service queries failed)", len(live), len(failed))

    summary = validate(manifest, live, failed_services=failed, statuses=statuses)
    logger.info(
        "Validation: %d checked, %d exact, %d lower(err), %d higher(warn), %d missing, %d incomplete",
        summary.total_checked, summary.passed, summary.errors,
        summary.warnings, summary.missing, summary.query_failed,
    )

    profile = "resource-principal" if ctx.signer is not None else os.environ.get("OCI_PROFILE", "DEFAULT")
    meta = RunMetadata(
        check="validate-limits",
        overall_status=overall_status(summary),
        profile=profile,
        tenancy=ctx.tenancy_id,
        region=ctx.region,
        workbooks=str(manifest_path),
        generated=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        services_completed=f"{len(services)}/{len(services)}",
    )

    render_readiness_html(summary, cfg, reports_dir / "DRCC-Region-Readiness-Report.html")
    render_readiness_pdf(summary, cfg, reports_dir / "DRCC-Region-Readiness-Report.pdf")
    render_validate_limits_pdf(summary, meta, reports_dir / "Validation-Limits-Report.pdf")
    render_validate_limits_html(summary, meta, reports_dir / "Validation-Limits-Report.html")
    logger.info("Reports written to %s", reports_dir)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="DRCC service limits validation")
    # str(): argparse default must be a string; artifacts_dir() returns a Path
    # and resolves the prod workspace dir (GENERIC_TESTS_WORKSPACE_DIR) when set.
    parser.add_argument("--output", default=str(artifacts_dir()))
    parser.add_argument("--manifest", default=os.environ.get("MANIFEST_PATH", DEFAULT_MANIFEST))
    parser.add_argument("--config", default=os.environ.get("CONFIG_PATH", DEFAULT_CONFIG))
    args = parser.parse_args()
    summary = run_validation(args.output, args.manifest, args.config)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
