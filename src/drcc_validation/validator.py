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
    MISSING = "Missing"


# Lower rank sorts first (most severe first) for findings tables.
SEVERITY_RANK = {
    Status.ERROR: 0,
    Status.WARNING: 1,
    Status.MISSING: 2,
    Status.INCOMPLETE: 3,
    Status.PASS: 4,
}


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
    message: str = ""


@dataclass
class ServiceSummary:
    service: str
    checked: int = 0
    passed: int = 0        # exact matches
    errors: int = 0        # lower than manifest
    warnings: int = 0      # higher than manifest
    incomplete: int = 0    # not validated (missing + query_failed); kept for readiness
    missing: int = 0       # live value absent though the query succeeded
    query_failed: int = 0  # the OCI query for this service failed
    overall_status: Status = Status.PASS
    commands_recorded: int = 0
    command_types: tuple[str, ...] = ()
    collection_status: tuple[tuple[str, int], ...] = ()


@dataclass
class ValidationSummary:
    results: list[LimitResult] = field(default_factory=list)
    services: list[ServiceSummary] = field(default_factory=list)
    total_checked: int = 0
    passed: int = 0
    errors: int = 0
    warnings: int = 0
    incomplete: int = 0
    missing: int = 0
    query_failed: int = 0


def _status_for(expected: int, actual: int) -> Status:
    if actual == expected:
        return Status.PASS
    if actual < expected:
        return Status.ERROR
    return Status.WARNING


def _service_overall(s: ServiceSummary) -> Status:
    if s.errors or s.missing:
        return Status.ERROR
    if s.warnings:
        return Status.WARNING
    if s.query_failed:
        return Status.INCOMPLETE
    return Status.PASS


def validate(
    manifest: list[ManifestLimit],
    live: list[LiveLimitValue],
    failed_services=frozenset(),
    statuses=None,
) -> ValidationSummary:
    """Compare each manifest limit against summed live values (all limits are
    scoped to global). ``failed_services`` is the set of services whose OCI
    query failed — their limits are reported Incomplete rather than Missing.
    ``statuses`` maps service -> ServiceQueryStatus for collection-status detail.
    """
    failed_services = set(failed_services or ())
    statuses = statuses or {}

    live_by_key: dict[tuple[str, str], list[LiveLimitValue]] = defaultdict(list)
    for v in live:
        live_by_key[(v.service, v.name)].append(v)

    results: list[LimitResult] = []
    for ml in manifest:
        if ml.service in failed_services:
            results.append(
                LimitResult(
                    ml.service, ml.limit, ml.description, ml.expected_value,
                    None, "MISSING", None, Status.INCOMPLETE,
                    f"One or more OCI queries for service {ml.service} did not "
                    f"complete, so {ml.limit} could not be validated.",
                )
            )
            continue
        matches = live_by_key.get((ml.service, ml.limit), [])
        if not matches:
            results.append(
                LimitResult(
                    ml.service, ml.limit, ml.description, ml.expected_value,
                    None, "MISSING", None, Status.MISSING,
                    f"Manifest limit {ml.limit} has no live value in service "
                    f"{ml.service}.",
                )
            )
            continue
        # All limits are scoped to global: sum the live values into a region
        # total and compare once against the manifest expectation.
        total = sum(v.value for v in matches)
        status = _status_for(ml.expected_value, total)
        verb = "matches" if status is Status.PASS else "differs from"
        results.append(
            LimitResult(
                ml.service, ml.limit, ml.description, ml.expected_value,
                total, "GLOBAL", None, status,
                f"live value {total} {verb} the manifest expectation.",
            )
        )

    svc_map: dict[str, ServiceSummary] = {}
    summary = ValidationSummary(results=results)
    for r in results:
        s = svc_map.setdefault(r.service, ServiceSummary(r.service))
        s.checked += 1
        summary.total_checked += 1
        if r.status is Status.PASS:
            s.passed += 1
            summary.passed += 1
        elif r.status is Status.ERROR:
            s.errors += 1
            summary.errors += 1
        elif r.status is Status.WARNING:
            s.warnings += 1
            summary.warnings += 1
        elif r.status is Status.MISSING:
            s.missing += 1
            summary.missing += 1
            s.incomplete += 1
            summary.incomplete += 1
        else:  # INCOMPLETE (query failed)
            s.query_failed += 1
            summary.query_failed += 1
            s.incomplete += 1
            summary.incomplete += 1

    for s in svc_map.values():
        s.overall_status = _service_overall(s)
        st = statuses.get(s.service)
        if st is not None:
            s.command_types = st.command_types
            s.commands_recorded = sum(count for _, count in st.collection_status)
            s.collection_status = st.collection_status

    summary.services = sorted(
        svc_map.values(), key=lambda s: (-s.errors, -s.warnings, s.service)
    )
    return summary
