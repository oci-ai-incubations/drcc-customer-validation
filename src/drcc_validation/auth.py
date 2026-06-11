"""Build OCI auth context for dev (config file) or prod (resource principal)."""
from __future__ import annotations

import os
from dataclasses import dataclass

import oci


@dataclass
class OciContext:
    config: dict
    signer: object | None
    tenancy_id: str
    region: str


def build_oci_context(env: str | None = None) -> OciContext:
    env = (env or os.environ.get("OCI_ENV", "dev")).strip().lower()

    if env == "prod":
        signer = oci.auth.signers.get_resource_principals_signer()
        tenancy = os.environ.get("OCI_TENANCY") or getattr(signer, "tenancy_id", "")
        region = (
            os.environ.get("OCI_REGION")
            or os.environ.get("OCI_RESOURCE_PRINCIPAL_REGION")
            or getattr(signer, "region", "")
        )
        return OciContext(config={"region": region}, signer=signer,
                          tenancy_id=tenancy, region=region)

    profile = os.environ.get("OCI_PROFILE", "DEFAULT")
    config = oci.config.from_file(profile_name=profile)
    return OciContext(
        config=config,
        signer=None,
        tenancy_id=config["tenancy"],
        region=config.get("region", ""),
    )


def build_limits_client(ctx: OciContext):
    if ctx.signer is not None:
        return oci.limits.LimitsClient(config=ctx.config, signer=ctx.signer)
    return oci.limits.LimitsClient(ctx.config)
