from pathlib import Path
from drcc_validation.manifest import ManifestLimit, load_manifest

MANIFEST = Path(__file__).resolve().parents[1] / "manifest" / "Default_Limits.xlsx"

def test_load_manifest_returns_all_rows():
    limits = load_manifest(MANIFEST)
    assert len(limits) == 612

def test_first_row_parsed_correctly():
    limits = load_manifest(MANIFEST)
    first = limits[0]
    assert isinstance(first, ManifestLimit)
    assert first.service == "big-data"
    assert first.limit == "bm-optimized3-36-memory-gb-size"
    assert first.description == "BM.Optimized3.36 - Total Memory in GBs"
    assert first.is_spending_limit is False
    assert first.is_managed_by_operator is True
    assert first.expected_value == 0

def test_unique_service_count():
    limits = load_manifest(MANIFEST)
    assert len({l.service for l in limits}) == 82
