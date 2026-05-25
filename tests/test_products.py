from datetime import datetime

import pytest

from products import REGISTRY


AT_TIME = datetime(2026, 5, 25, 23, 59)


@pytest.mark.parametrize("pid", list(REGISTRY))
def test_simulate_with_defaults_runs(pid):
    sim = REGISTRY[pid].simulate({}, AT_TIME)
    assert sim.aggregate_metrics
    assert isinstance(sim.eligible_targets, list)
    assert isinstance(sim.per_target_outcomes, list)


def test_captive_yield_sums_per_target():
    sim = REGISTRY["captive_invoice_financing"].simulate({}, AT_TIME)
    per = sum(o["contribution_amount"] for o in sim.per_target_outcomes)
    assert abs(per - sim.aggregate_metrics["total_yield_annualised_pkr"]) < 1.0


def test_securitised_rail_compresses_friction():
    bank = REGISTRY["securitised_yield_originator"].simulate(
        {"settlement_rail": "bank"}, AT_TIME).aggregate_metrics
    stable = REGISTRY["securitised_yield_originator"].simulate(
        {"settlement_rail": "stablecoin"}, AT_TIME).aggregate_metrics
    assert stable["ccc_days_at_rail"] < bank["ccc_days_at_rail"]
    assert stable["settlement_rail_value_pkr"] >= bank["settlement_rail_value_pkr"]
