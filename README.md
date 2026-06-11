# DRCC Customer Validation — Service Limits

Validates an OCI region's service limits against `manifest/Default_Limits.xlsx`
and generates a **DRCC Region Readiness report** (HTML + PDF) and a detailed
**Validation Limits report** (PDF).

## Status semantics
Pass = matches manifest · Error = below manifest · Warning = above manifest ·
Incomplete = no live value returned. (`strict: true` makes the suite fail the
build when any limit is below the manifest.)

## Auth modes (`OCI_ENV`)
- `dev` (default): uses `~/.oci/config` profile `OCI_PROFILE` (default `DEFAULT`).
- `prod`: uses resource-principal auth (run inside OCI with an RP-enabled
  dynamic group); no key files needed. Tenancy/region come from the RP signer;
  override with `OCI_TENANCY` / `OCI_REGION`.

## Run locally (recommended for dev)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
OCI_ENV=dev PYTHONPATH=src .venv/bin/pytest -m integration -v
open output/DRCC-Region-Readiness-Report.html
```
Or run the CLI directly:
```bash
OCI_ENV=dev PYTHONPATH=src .venv/bin/python -m drcc_validation.cli --output output
```

## Run in Docker

### prod (resource principal) — the primary container use case
```bash
docker build -t drcc-validate .
docker run --rm -e OCI_ENV=prod -v "$PWD/output:/app/output" drcc-validate
```

### Verify the image without OCI (unit tests only)
```bash
docker run --rm drcc-validate pytest -m "not integration" -v
```

### dev (API-key profile) in Docker — caveat
`~/.oci/config` references private keys by **absolute host path**
(e.g. `/Users/you/.oci/oci_api_key.pem`). For those paths to resolve inside the
container, mount your `.oci` directory at the **same absolute path** the config
points to, e.g.:
```bash
docker run --rm -e OCI_ENV=dev \
  -v "$HOME/.oci:$HOME/.oci:ro" -e "HOME=$HOME" \
  -v "$PWD/output:/app/output" drcc-validate
```
(The simplest dev workflow remains the local venv above.)

## Report metadata
Edit `config/report_config.yaml` or override per-field with env vars
(`REPORT_CUSTOMER_NAME`, `REPORT_REGION_LABEL`, `REPORT_GA_TARGET_DATE`,
`REPORT_JIRA_URL`, `REPORT_STRICT`). Region label auto-detects from the
authenticated region when left blank.

## Outputs (in `output/`)
- `DRCC-Region-Readiness-Report.html` — interactive 4-view report (Chart.js)
- `DRCC-Region-Readiness-Report.pdf` — print version
- `Validation-Limits-Report.pdf` — detailed per-limit results
