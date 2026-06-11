"""Live OCI limit values."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LiveLimitValue:
    service: str
    name: str
    scope_type: str            # GLOBAL | REGION | AD
    availability_domain: str | None
    value: int
