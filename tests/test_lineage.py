from datetime import datetime

from backend import lineage
from derived.ots import OTS


AT_TIME = datetime(2026, 5, 25, 23, 59)


def test_store_and_decompose_roundtrip():
    r = OTS.compute_cached("SUP-001", AT_TIME)
    assert r.computation_id is not None
    decomp = lineage.decompose(r.computation_id, depth=2)
    assert decomp["entity_type"] == "ots"
    assert decomp["entity_id"] == "SUP-001"
    assert decomp["children"], "expected at least one input branch"
    for child in decomp["children"]:
        assert child["kind"] in {"leaf", "computation"}


def test_lookup_returns_cached_result():
    OTS.compute_cached("SUP-001", AT_TIME)
    cached = lineage.lookup("ots", "SUP-001", AT_TIME, OTS.FORMULA_VERSION)
    assert cached is not None
    assert cached.entity_id == "SUP-001"
