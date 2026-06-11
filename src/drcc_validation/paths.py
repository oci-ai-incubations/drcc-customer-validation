"""Resolve where run artifacts are written, preferring the prod workspace volume.

Precedence (highest first):
  GENERIC_TESTS_WORKSPACE_DIR  — set by the prod Generic Tests framework
  OUTPUT_DIR                   — dev / docker-compose
  "output"                     — local default (cwd-relative)
"""
from __future__ import annotations

import os
from pathlib import Path


def artifacts_dir() -> Path:
    """Base directory for all run artifacts."""
    return Path(
        os.environ.get("GENERIC_TESTS_WORKSPACE_DIR")
        or os.environ.get("OUTPUT_DIR")
        or "output"
    )


def reports_dir() -> Path:
    """Where the customer reports are written."""
    return artifacts_dir() / "reports"


def logs_dir() -> Path:
    """Where run logs / JUnit results are written."""
    return artifacts_dir() / "logs"
