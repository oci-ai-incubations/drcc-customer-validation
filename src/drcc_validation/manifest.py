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
                expected_value=int(float(row[5])) if row[5] is not None else 0,
            )
        )
    wb.close()
    return limits
