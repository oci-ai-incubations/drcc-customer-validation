from types import SimpleNamespace
from drcc_validation.limits_client import LiveLimitValue, fetch_live_limits


class FakeClient:
    """Stands in for oci.limits.LimitsClient; records calls."""
    def __init__(self, values_by_service):
        self.values_by_service = values_by_service
        self.calls = []

    def list_limit_values(self, compartment_id, service_name=None, **kwargs):
        self.calls.append((compartment_id, service_name))
        return service_name


def fake_pager(list_func, compartment_id, service_name=None, **kwargs):
    # mimic oci.pagination.list_call_get_all_results(...).data
    svc = list_func(compartment_id, service_name=service_name)
    items = client_values[svc]
    return SimpleNamespace(data=items)


client_values = {
    "compute": [
        SimpleNamespace(name="cores", scope_type="AD", availability_domain="AD-1", value=10),
        SimpleNamespace(name="cores", scope_type="AD", availability_domain="AD-2", value=4),
    ],
    "vcn": [
        SimpleNamespace(name="subnets", scope_type="REGION", availability_domain=None, value=5),
    ],
}


def test_fetch_live_limits_flattens_all_services(monkeypatch):
    import drcc_validation.limits_client as lc
    monkeypatch.setattr(lc.oci.pagination, "list_call_get_all_results", fake_pager)
    client = FakeClient(client_values)
    out = fetch_live_limits(client, "ocid1.tenancy.oc1..t", ["compute", "vcn"])
    assert LiveLimitValue("compute", "cores", "AD", "AD-1", 10) in out
    assert LiveLimitValue("compute", "cores", "AD", "AD-2", 4) in out
    assert LiveLimitValue("vcn", "subnets", "REGION", None, 5) in out
    assert len(out) == 3
    assert ("ocid1.tenancy.oc1..t", "compute") in client.calls


def test_fetch_skips_values_with_none_value(monkeypatch):
    import drcc_validation.limits_client as lc
    monkeypatch.setattr(lc.oci.pagination, "list_call_get_all_results", fake_pager)
    client_values["empty"] = [
        SimpleNamespace(name="x", scope_type="REGION", availability_domain=None, value=None),
    ]
    client = FakeClient(client_values)
    out = fetch_live_limits(client, "t", ["empty"])
    assert out == []
