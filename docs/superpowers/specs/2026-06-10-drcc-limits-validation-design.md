# DRCC Customer Validation — Service Limits Validation & Reporting

**Date:** 2026-06-10
**Status:** Approved (design)

## Purpose

Validate that an OCI region's configured service limits match a contracted
manifest (`manifest/Default_Limits.xlsx`), and produce two customer-facing
reports: a **DRCC Region Readiness report** and a detailed **Validation Limits
report**. The tool runs as a containerized pytest suite that works against a
local OCI config profile in development and resource-principal auth in
production.

## Inputs

### Manifest — `manifest/Default_Limits.xlsx`
Single sheet, 613 rows (612 data rows), 82 unique services. Columns:

| Column | Meaning |
|--------|---------|
| `Service` | OCI limits service name (e.g. `compute`, `database`) |
| `Limit` | Limit name (e.g. `bm-optimized3-36-ocpu-count`) |
| `Description` | Human-readable limit description |
| `Is Spending Limits?` | bool (33 rows true) |
| `Is Managed By Operator?` | bool (502 rows true) |
| `DefaultValue(ND)` | Expected default limit value to compare against |

### OCI config
`~/.oci/config`, `DEFAULT` profile (API-key auth, region `us-ashburn-1`).

## Authentication — `OCI_ENV` environment variable

- `dev` (default): `oci.config.from_file(profile_name=OCI_PROFILE)` where
  `OCI_PROFILE` defaults to `DEFAULT`. Tenancy + region come from the profile.
- `prod`: `oci.auth.signers.get_resource_principals_signer()`; clients built with
  `config={}, signer=signer`. Tenancy and region derived from the signer, with
  optional env overrides (`OCI_TENANCY`, `OCI_REGION`).

`auth.py` exposes a single factory returning `(config, signer, tenancy_id, region)`
so the rest of the code is auth-mode agnostic.

## Validation flow

1. **Load manifest** → list of rows keyed by `(service, limit)` with expected value.
2. **Query live limits**: for each of the 82 unique services call
   `LimitsClient.list_limit_values(compartment_id=<tenancy>, service_name=svc)`,
   paginated via `oci.pagination.list_call_get_all_results`. Collect actual values
   keyed by `(service, limit_name, scope_type, availability_domain)`.
3. **Compare** each manifest row against matching live value(s). Status semantics
   (taken directly from the HTML template legend):
   - `actual == expected` → **Pass** (matches manifest)
   - `actual < expected` → **Error** (lower than contracted)
   - `actual > expected` → **Warning** (higher than manifest)
   - no live value found → **Incomplete** (live data unavailable)
4. **Aggregate** per-service counts (checked / pass / error / warning / incomplete)
   and grand totals for the executive summary and charts.

A limit value may be region- or AD-scoped; each returned `(scope, AD)` value is a
distinct check, so one manifest row can expand to several checks. When no live
value exists for a manifest limit, it counts as one Incomplete check.

## Components (`src/drcc_validation/`)

| Module | Responsibility | Depends on |
|--------|----------------|------------|
| `auth.py` | Build OCI config/signer + tenancy/region from `OCI_ENV` | `oci` |
| `manifest.py` | Parse the xlsx into `ManifestLimit` records | `openpyxl` |
| `limits_client.py` | Query `list_limit_values` per service → `LiveLimitValue` records | `oci`, `auth` |
| `validator.py` | Compare manifest vs live → `LimitResult` + `ValidationSummary` | pure Python |
| `config.py` | Load `report_config.yaml` with per-field env overrides | `pyyaml` |
| `reports/readiness.py` | Render Region Readiness HTML + PDF | `jinja2`, `weasyprint`, `matplotlib` |
| `reports/limits_report.py` | Render detailed limits PDF | `jinja2`, `weasyprint` |
| `reports/templates/` | Jinja2 templates (reuse existing CSS) + chart helpers | — |
| `cli.py` | Orchestrate: auth → query → validate → render reports | all of the above |

`validator.py` is pure and fully unit-testable with fixtures; it has no OCI
dependency. `limits_client.py` is the only module that performs live calls.

## Reports (written to `output/`)

### DRCC Region Readiness report
Data-driven version of `DRCC-Region-Readiness-Report-Templates.html` (4 views:
Executive, Scorecard, Detailed+Charts, Certificate). Produced as:
- **HTML** — interactive, Chart.js (matches the existing template exactly).
- **PDF** — same layout via WeasyPrint; charts pre-rendered as matplotlib PNGs
  (WeasyPrint does not execute JavaScript).

### Validation Limits report (PDF)
Per-service tables listing every limit with columns: Limit, Description, Expected,
Actual, Scope, Availability Domain, Status. Includes a summary page (totals +
per-service rollup). Rendered via the same HTML→WeasyPrint path.

## Report metadata — `config/report_config.yaml`
Fields: `customer_name`, `region_label`, `ga_target_date`, `validation_run_date`,
`contacts[]` (name, role, email), `jira_url`, `strict` (fail build on errors).
Each field overridable by an env var (e.g. `REPORT_CUSTOMER_NAME`). Region label
falls back to the auto-detected region from auth.

## Testing

- `tests/test_manifest.py` — manifest parsing (real fixture xlsx).
- `tests/test_validator.py` — comparison logic across all four statuses, per-AD
  expansion, aggregation; uses in-memory fixtures (no OCI).
- `tests/test_config.py` — config loading + env overrides.
- `tests/test_limits_validation.py` — the live integration test (marked
  `integration`): authenticates, queries OCI, validates, **always generates both
  reports** (via a fixture finalizer so reports exist even on failure), then
  asserts `summary.errors == 0` when `strict` is set.

Unit tests run with no cloud access. The Docker `CMD` runs the full suite.

## Docker

- Base `python:3.12-slim` + WeasyPrint system libs
  (`libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info libcairo2`).
- `pip install -r requirements.txt`.
- `dev`: mount `~/.oci` read-only and `./output`; pass `OCI_ENV=dev`.
- `prod`: no config mount; `OCI_ENV=prod` uses resource principal.
- Metadata + `OCI_ENV`/`OCI_PROFILE` passed as env vars.
- `CMD ["pytest", "-v", "--junitxml=output/results.xml"]`.

## Dependencies (`requirements.txt`)
`oci`, `openpyxl`, `pyyaml`, `jinja2`, `weasyprint`, `matplotlib`, `pytest`.

## Out of scope
- Remediating limits (read/validate only).
- Non-limit DRCC checks (network, IAM, etc.).
- Uploading reports anywhere (written to local `output/`).
