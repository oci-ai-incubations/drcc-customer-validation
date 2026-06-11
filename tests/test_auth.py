import drcc_validation.auth as auth
from drcc_validation.auth import build_oci_context


def test_dev_uses_config_file(monkeypatch):
    fake_cfg = {"tenancy": "ocid1.tenancy.oc1..t", "region": "us-ashburn-1"}
    monkeypatch.setattr(auth.oci.config, "from_file", lambda profile_name: fake_cfg)
    monkeypatch.setenv("OCI_ENV", "dev")
    monkeypatch.setenv("OCI_PROFILE", "DEFAULT")
    ctx = build_oci_context()
    assert ctx.signer is None
    assert ctx.tenancy_id == "ocid1.tenancy.oc1..t"
    assert ctx.region == "us-ashburn-1"


def test_prod_uses_resource_principal(monkeypatch):
    class FakeSigner:
        tenancy_id = "ocid1.tenancy.oc1..rp"
        region = "us-phoenix-1"

    monkeypatch.setattr(
        auth.oci.auth.signers,
        "get_resource_principals_signer",
        lambda: FakeSigner(),
    )
    monkeypatch.setenv("OCI_ENV", "prod")
    monkeypatch.delenv("OCI_TENANCY", raising=False)
    monkeypatch.delenv("OCI_REGION", raising=False)
    ctx = build_oci_context()
    assert ctx.signer is not None
    assert ctx.tenancy_id == "ocid1.tenancy.oc1..rp"
    assert ctx.region == "us-phoenix-1"


def test_prod_env_overrides(monkeypatch):
    class FakeSigner:
        tenancy_id = "ocid1.tenancy.oc1..rp"
        region = "us-phoenix-1"

    monkeypatch.setattr(
        auth.oci.auth.signers,
        "get_resource_principals_signer",
        lambda: FakeSigner(),
    )
    monkeypatch.setenv("OCI_ENV", "prod")
    monkeypatch.setenv("OCI_TENANCY", "ocid1.tenancy.oc1..override")
    monkeypatch.setenv("OCI_REGION", "uk-london-1")
    ctx = build_oci_context()
    assert ctx.tenancy_id == "ocid1.tenancy.oc1..override"
    assert ctx.region == "uk-london-1"
