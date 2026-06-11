from drcc_validation.manifest import ManifestLimit
from drcc_validation.limits_client import LiveLimitValue
from drcc_validation.validator import Status, validate


def m(service, limit, expected):
    return ManifestLimit(service, limit, f"{limit} desc", False, True, expected)


def live(service, name, value, scope="REGION", ad=None):
    return LiveLimitValue(service, name, scope, ad, value)


def test_pass_when_equal():
    summary = validate([m("compute", "cores", 10)], [live("compute", "cores", 10)])
    assert summary.results[0].status == Status.PASS
    assert summary.passed == 1 and summary.total_checked == 1


def test_error_when_actual_lower():
    summary = validate([m("compute", "cores", 10)], [live("compute", "cores", 4)])
    assert summary.results[0].status == Status.ERROR
    assert summary.errors == 1


def test_warning_when_actual_higher():
    summary = validate([m("compute", "cores", 10)], [live("compute", "cores", 99)])
    assert summary.results[0].status == Status.WARNING
    assert summary.warnings == 1


def test_incomplete_when_no_live_value():
    summary = validate([m("vcn", "subnets", 5)], [])
    r = summary.results[0]
    assert r.status == Status.INCOMPLETE
    assert r.actual is None
    assert summary.incomplete == 1


def test_per_ad_values_summed_into_one_global_check():
    # All limits are scoped to global: per-AD values are summed into a single
    # region total and compared once against the manifest's expected value.
    manifest = [m("compute", "cores", 10)]
    values = [
        live("compute", "cores", 6, scope="AD", ad="AD-1"),
        live("compute", "cores", 6, scope="AD", ad="AD-2"),
    ]
    summary = validate(manifest, values)
    assert summary.total_checked == 1          # one global check, not per-AD
    r = summary.results[0]
    assert r.actual == 12                       # 6 + 6 summed
    assert r.scope_type == "GLOBAL"
    assert r.availability_domain is None
    assert r.status == Status.WARNING           # 12 > expected 10
    assert summary.warnings == 1


def test_sum_equal_to_expected_passes():
    manifest = [m("compute", "cores", 12)]
    values = [
        live("compute", "cores", 4, scope="AD", ad="AD-1"),
        live("compute", "cores", 4, scope="AD", ad="AD-2"),
        live("compute", "cores", 4, scope="AD", ad="AD-3"),
    ]
    summary = validate(manifest, values)
    assert summary.total_checked == 1
    assert summary.results[0].actual == 12
    assert summary.results[0].status == Status.PASS


def test_per_service_summary_rollup():
    manifest = [m("compute", "a", 10), m("compute", "b", 10), m("vcn", "c", 1)]
    values = [
        live("compute", "a", 10),
        live("compute", "b", 4),
        live("vcn", "c", 1),
    ]
    summary = validate(manifest, values)
    by_service = {s.service: s for s in summary.services}
    assert by_service["compute"].checked == 2
    assert by_service["compute"].passed == 1
    assert by_service["compute"].errors == 1
    assert by_service["vcn"].passed == 1
