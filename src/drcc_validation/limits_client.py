"""Live OCI limit values."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import oci

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveLimitValue:
    service: str
    name: str
    scope_type: str            # GLOBAL | REGION | AD
    availability_domain: str | None
    value: int


@dataclass(frozen=True)
class ServiceQueryStatus:
    """Outcome of querying one service's limit values."""
    service: str
    ok: bool
    command_types: tuple[str, ...]
    # (status_string, count) pairs, e.g. ("returncode:0", 1) or a ServiceError line.
    collection_status: tuple[tuple[str, int], ...]


def _service_error_line(exc) -> str:
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None)
    if code is not None and status is not None:
        return (f"ServiceError code:{code} status:{status} "
                f"operation_name:list_limit_values")
    return f"{type(exc).__name__} operation_name:list_limit_values"


def fetch_live_limits_with_status(
    limits_client, compartment_id: str, services: list[str]
) -> tuple[list[LiveLimitValue], dict[str, ServiceQueryStatus]]:
    """Query list_limit_values per service; return flattened values plus a
    per-service query status, so the caller can distinguish a service whose
    query failed (Incomplete) from one that simply returned no value for a
    limit (Missing)."""
    out: list[LiveLimitValue] = []
    statuses: dict[str, ServiceQueryStatus] = {}
    for service in services:
        try:
            resp = oci.pagination.list_call_get_all_results(
                limits_client.list_limit_values,
                compartment_id,
                service_name=service,
            )
        except (oci.exceptions.ServiceError, oci.exceptions.RequestException) as exc:
            logger.warning("Failed to fetch limits for %s: %s", service, exc)
            statuses[service] = ServiceQueryStatus(
                service=service,
                ok=False,
                command_types=("limits-value-list",),
                collection_status=((_service_error_line(exc), 1),),
            )
            continue
        for item in resp.data:
            if getattr(item, "value", None) is None:
                continue
            out.append(
                LiveLimitValue(
                    service=service,
                    name=item.name,
                    scope_type=item.scope_type,
                    availability_domain=item.availability_domain,
                    value=int(item.value),
                )
            )
        statuses[service] = ServiceQueryStatus(
            service=service,
            ok=True,
            command_types=("limits-value-list",),
            collection_status=(("returncode:0", 1),),
        )
    return out, statuses


def fetch_live_limits(
    limits_client, compartment_id: str, services: list[str]
) -> list[LiveLimitValue]:
    """Query list_limit_values for each service; flatten to LiveLimitValue records."""
    return fetch_live_limits_with_status(limits_client, compartment_id, services)[0]


def unique_services(manifest_limits) -> list[str]:
    seen: dict[str, None] = {}
    for ml in manifest_limits:
        seen.setdefault(ml.service, None)
    return list(seen)
