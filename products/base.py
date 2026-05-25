"""Shared types for credit products. See SPEC §5 / CLAUDE.md §3."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProductSimulation:
    eligible_targets: list[dict]
    aggregate_metrics: dict
    per_target_outcomes: list[dict]
    parameter_traces: dict = field(default_factory=dict)


SETTLEMENT_RAILS = {
    "bank":       {"settlement_latency": 3, "processing_overhead": 2},
    "raast":      {"settlement_latency": 0, "processing_overhead": 1},
    "stablecoin": {"settlement_latency": 0, "processing_overhead": 0},
}
