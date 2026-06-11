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


def fetch_live_limits(
    limits_client, compartment_id: str, services: list[str]
) -> list[LiveLimitValue]:
    """Query list_limit_values for each service; flatten to LiveLimitValue records."""
    out: list[LiveLimitValue] = []
    for service in services:
        try:
            resp = oci.pagination.list_call_get_all_results(
                limits_client.list_limit_values,
                compartment_id,
                service_name=service,
            )
        except oci.exceptions.ServiceError as exc:
            logger.warning("Failed to fetch limits for %s: %s", service, exc)
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
    return out


def unique_services(manifest_limits) -> list[str]:
    seen: dict[str, None] = {}
    for ml in manifest_limits:
        seen.setdefault(ml.service, None)
    return list(seen)
