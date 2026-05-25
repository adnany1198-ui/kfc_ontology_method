from datetime import datetime

import pytest

from derived import REGISTRY
from derived.ots import OTS, _tier


AT_TIME = datetime(2026, 5, 25, 23, 59)


def test_tier_grid():
    assert _tier(0.95) == "A"
    assert _tier(0.88) == "B"
    assert _tier(0.80) == "C"
    assert _tier(0.50) == "D"


def test_ots_components_present_for_known_supplier():
    r = OTS.compute("SUP-001", AT_TIME)
    assert isinstance(r.value, float)
    for k in ("on_time_rate", "fill_rate", "quality_pass_rate",
              "volume_consistency", "payment_compliance", "tier"):
        assert k in r.components


@pytest.mark.parametrize("entity_type", ["ots", "soy", "dpi"])
def test_per_supplier_entities_run_for_every_supplier(entity_type):
    cls = REGISTRY[entity_type]
    for sup in cls.list_targets():
        r = cls.compute_cached(sup, AT_TIME)
        assert r.formula_version == cls.FORMULA_VERSION
        # Either a numeric value or an insufficient-data dict.
        assert isinstance(r.value, (int, float, dict))


def test_ccc_rails_differ():
    bank = REGISTRY["ccc"].compute("system", AT_TIME, rail="bank").value
    stable = REGISTRY["ccc"].compute("system", AT_TIME, rail="stablecoin").value
    assert bank > stable, "stablecoin should compress the conversion cycle"
