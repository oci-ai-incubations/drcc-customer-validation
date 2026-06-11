"""Compare manifest limits against live OCI limit values."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from .limits_client import LiveLimitValue
from .manifest import ManifestLimit


class Status(str, Enum):
    PASS = "Pass"
    ERROR = "Error"
    WARNING = "Warning"
    INCOMPLETE = "Incomplete"


@dataclass(frozen=True)
class LimitResult:
    service: str
    limit: str
    description: str
    expected: int
    actual: int | None
    scope_type: str | None
    availability_domain: str | None
    status: Status


@dataclass
class ServiceSummary:
    service: str
    checked: int = 0
    passed: int = 0
    errors: int = 0
    warnings: int = 0
    incomplete: int = 0


@dataclass
class ValidationSummary:
    results: list[LimitResult] = field(default_factory=list)
    services: list[ServiceSummary] = field(default_factory=list)
    total_checked: int = 0
    passed: int = 0
    errors: int = 0
    warnings: int = 0
    incomplete: int = 0


def _status_for(expected: int, actual: int) -> Status:
    if actual == expected:
        return Status.PASS
    if actual < expected:
        return Status.ERROR
    return Status.WARNING


def validate(
    manifest: list[ManifestLimit], live: list[LiveLimitValue]
) -> ValidationSummary:
    live_by_key: dict[tuple[str, str], list[LiveLimitValue]] = defaultdict(list)
    for v in live:
        live_by_key[(v.service, v.name)].append(v)

    results: list[LimitResult] = []
    for ml in manifest:
        matches = live_by_key.get((ml.service, ml.limit), [])
        if not matches:
            results.append(
                LimitResult(
                    ml.service, ml.limit, ml.description, ml.expected_value,
                    None, None, None, Status.INCOMPLETE,
                )
            )
            continue
        for v in matches:
            results.append(
                LimitResult(
                    ml.service, ml.limit, ml.description, ml.expected_value,
                    v.value, v.scope_type, v.availability_domain,
                    _status_for(ml.expected_value, v.value),
                )
            )

    svc_map: dict[str, ServiceSummary] = {}
    summary = ValidationSummary(results=results)
    for r in results:
        s = svc_map.setdefault(r.service, ServiceSummary(r.service))
        s.checked += 1
        summary.total_checked += 1
        if r.status == Status.PASS:
            s.passed += 1
            summary.passed += 1
        elif r.status == Status.ERROR:
            s.errors += 1
            summary.errors += 1
        elif r.status == Status.WARNING:
            s.warnings += 1
            summary.warnings += 1
        else:
            s.incomplete += 1
            summary.incomplete += 1

    summary.services = sorted(
        svc_map.values(), key=lambda s: (-s.errors, -s.warnings, s.service)
    )
    return summary
