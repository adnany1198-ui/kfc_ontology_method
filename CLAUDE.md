# CLAUDE.md — Agent brief for the KFC Ontology build

You are working on a Streamlit prototype that demonstrates a methodology for
turning KFC Pakistan operational data into the data layer for credit product
simulations. Read `SPEC.md` for the full specification and `METHODOLOGY.md`
for the strategic frame.

This document captures **binding resolutions** to ambiguities in `SPEC.md`.
Where this file and `SPEC.md` disagree, this file wins.

---

## 1. Data sources

### Real POS — Railway endpoint

Base URL: `https://cv2-production-008f.up.railway.app`

- `/` — status, transaction count, latest transaction
- `/latest` — last 20 transactions
- `/transactions` — full dataset (~57k+ records, slow)
- `/transactions?store_id=0062` — filter by store (4-digit zero-padded)
- `/transactions?till_id=1088` — filter by till
- `/transactions?store_id=0062&till_id=1088` — both

**Store IDs are 4-digit zero-padded strings** (e.g. `0030`, `0047`, `0223`, `0249`).
**Till IDs are 3–4 digits**.

**Pull pattern for Phase 1:**

1. Hit `/` to confirm liveness and inspect payload shape.
2. Hit `/latest` to inspect transaction structure. Expected fields:
   `transaction_id, store_id, till_id, operator_id, timestamp, received_at,
   basket_value, item_count, payment_method, line_items[]`.
3. Pull full dataset via `/transactions`. If the receiver chokes on the full
   payload, paginate by iterating across all `store_id` values discovered in
   step 1/2.
4. Apply quality filters on load:
   - `basket_value > 0`
   - `basket_value < 50000`
   - line-item `quantity BETWEEN 1 AND 100`
5. **Channel encoding:** channel is embedded in product names
   (e.g. `"ZINGER BURGER EAT IN"`, `"ZINGER BURGER TAKE AWAY"`).
   Extract channel during loading; do not rely on a separate column.

### Synthetic seed CSVs

Live in `data/seed/`. Twelve CSVs (see `data/seed/README.md`).

- **`07_pos_daily.csv`** — keep on disk for reference, do **not** load into
  DuckDB. Real POS replaces it.
- **`08_ingredient_consumption_daily.csv`** — schema reference only.
  Will be regenerated as a derived table from real POS × recipes.
- **`09–12`** (POs, deliveries, invoices, payments) — load as-is for v1.
  Procurement chain references modelled `store_id`s that don't match real
  POS — flag this inconsistency on the About page. Regeneration deferred to v1.5.

### Real vs synthetic reconciliation

- **Stores:** keep only the 34 real stores in `store_summary`. Use the seed's
  `02_stores.csv` as supplemental metadata source (format, seats, region)
  joined by `store_id` where matches exist. Discard synthetic-only stores.
- **Store → commissary routing:** real POS `store_id`s not in seed get default
  routing — all assigned to `COM-KHI-01`. Flag this assumption on About page.
- **SKUs:** real POS supplies 419 menu items. Modelled supply chain has 31
  recipe templates. `sku_recipe_mapping` table bridges them. Keep modelled
  `skus` table as the recipe template domain.
- **Nodes:** locations are real (commissary in Sher Shah, cold/dry warehouses
  in Korangi); flows through them are modelled.

### Recipe mapping process

1. You generate fuzzy name matches between 419 real SKUs and 31 templates,
   each with a confidence score.
2. Write results to `data/sku_recipe_mapping_candidates.csv`.
3. Adnan reviews and edits the file.
4. You load the reviewed file into the `sku_recipe_mapping` table.
5. **Halt Phase 1 step 4 until Adnan signs off.**
6. **Coverage gate:** to proceed past step 4, ≥75% of POS revenue must map
   to recipes. If below, surface unmapped high-revenue SKUs for review.

### Quality variance injection

If the seed's `10_deliveries.csv` shows `quality_pass_qty == delivered_qty`
on every row, inject realistic variance during load:
- 92–100% pass rate per delivery
- Variance correlated to supplier (some consistently better than others)
- Document the injection in the load script

---

## 2. Time semantics

- **Cursor granularity:** daily.
- **Cursor default:** `max(observed POS event_time)`.
- **Cursor range:** intersection of observed and modelled time spans. If real
  POS is shorter, that's the window. If longer, cap at modelled end and surface
  the constraint in the cursor widget.
- **Forward-of-default events** (modelled invoices/payments past the POS end)
  are invisible at default; user scrubs forward to see them with a "projected"
  badge.
- **`event_time` column per table:**

  | Table                          | event_time column         |
  | ------------------------------ | ------------------------- |
  | `pos_transactions`             | `transaction_timestamp`   |
  | `pos_line_items`               | inherits from parent      |
  | `purchase_orders`              | `po_date`                 |
  | `deliveries`                   | `delivery_date`           |
  | `invoices`                     | `invoice_date`            |
  | `payments`                     | `payment_date`            |
  | `ingredient_consumption_daily` | `date`                    |

---

## 3. Lineage and computation

### `ComputationResult` dataclass

```python
from dataclasses import dataclass

@dataclass
class InputRef:
    value: float | int | str | dict
    source_table: str
    source_filter: str       # JSON-serialised
    source_row_count: int

@dataclass
class ComputationResult:
    value: float | dict
    components: dict[str, float]
    inputs: dict[str, InputRef]
    formula_version: str
```

### Storage

- `computations.output_value_numeric DOUBLE` and
  `computations.output_value_json VARCHAR` — populate one based on scalar
  vs structured.
- `computation_inputs.source_filter` — JSON-serialised dict. For Python
  aggregations, store the query equivalent
  (e.g. `{"op": "sum", "column": "amount_pkr", "filter": {...}}`).

### Caching

Memoize by `(entity_type, entity_id, at_time, formula_version)`. Recompute
on miss. Add an `is_stale` flag for invalidation when underlying data changes.

### `decompose()` return shape

```python
{
  "computation_id": str,
  "entity_type": str,
  "entity_id": str,
  "value": float | dict,
  "formula_version": str,
  "children": [InputNode | LeafNode]  # recursive
}
```

- `LeafNode`: `{source_table, source_filter, sample_rows}`
- `InputNode`: recursive (same shape as above)

### `query_data_layer` filter shape

Dict of `{column: value}` for equality. For more complex filters:
`{column: {"op": "gt"|"gte"|"lt"|"lte"|"in", "value": x}}`.

### `get_entity_history` granularity

One of `"daily" | "weekly" | "monthly"`.

### `ProductSimulation` shape

```python
@dataclass
class ProductSimulation:
    eligible_targets: list[dict]    # {target_id, included: bool, reason: str}
    aggregate_metrics: dict
    per_target_outcomes: list[dict] # {target_id, score_values, contribution_amount, rate_applied}
    parameter_traces: dict
```

---

## 4. Derived-entity corrections to SPEC.md

### OTS `payment_compliance` — redefined

Original spec references "disputed invoices"; the data has no dispute flag.
Use this instead:

```
payment_compliance = 1 - (count of invoices paid more than 7 days late / total invoices)
```

Computed from `12_payments.csv.days_vs_due`.

### SOY risk adjustment — corrected formula

Original spec formula gives a 94% haircut, which is wrong. Use this:

```
adjustment_factor = 0.5
risk_factor = 1 - ((1 - OTS_score) × adjustment_factor)
risk_adjusted = annualised × risk_factor
```

For OTS = 0.83: `risk_factor = 1 - (0.17 × 0.5) = 0.915`. Gives ~5% haircut
for A-tier, ~8.5% for B, ~15% for D.

### CCC `payment_terms_weighted_avg`

Weighted by COGS contribution — use sum of invoice amounts per supplier as
the COGS proxy.

### CCC fallback

If recipe coverage <75% at Phase 3, CCC uses a parameter-driven approximation
(industry-default food cost %) — flag the fallback in `components`.

### Settlement-rail parameter table

```python
SETTLEMENT_RAILS = {
    "bank":       {"settlement_latency": 3, "processing_overhead": 2},
    "raast":      {"settlement_latency": 0, "processing_overhead": 1},
    "stablecoin": {"settlement_latency": 0, "processing_overhead": 0},
}
```

---

## 5. User-constructed entities

### Operation semantics

| operation         | output per target | meaning                                                  |
| ----------------- | ----------------- | -------------------------------------------------------- |
| `weighted_sum`    | float             | sum of `input_value_i × weight_i`                        |
| `threshold`       | bool              | `score >= params.threshold`                              |
| `trend_direction` | float             | sign of slope of input series over `params.window_days`  |
| `rolling_average` | float             | mean of input values over `params.window_days`           |

### Scope

**Target-scoped only for v1.** System-wide user entities deferred.
`compute_user_entity(user_entity_id, target_id, at_time)` always requires
`target_id`. System-wide built-in entities (CCC) cannot be referenced from
user-constructed entities in v1.

### Plugging into credit products

User entities replace **score inputs**, not thresholds. Each product has a
default score input:

- Captive Invoice Financing → OTS
- Forward Credit → DPI
- Securitised Yield Originator → OTS

A user entity can be selected to replace the score input via dropdown in the
product simulator. The threshold remains a scalar applied to whatever score
is selected.

System-wide entities (like CCC) are not usable as eligibility scores — they
appear in the simulator's informational context only.

---

## 6. Streamlit conventions

- Page filenames use underscores, not spaces: `01_Data_Layer.py`.
  Streamlit renders underscores as spaces in the sidebar.
- `app.py` is the Overview page directly (no redirect).
- DB bootstrap: first-time setup is
  `python data/load.py` then `streamlit run app.py`.
  `app.py` checks for `data/kfc.duckdb` on startup; if missing, displays an
  error with the instruction to run `load.py`.

---

## 7. Drill-down

Use **Big Bird Foods (SUP-001)** as the deterministic representative supplier.
Hardcode the walk path; compute live values.

---

## 8. Build sequencing notes

- Phase 1 step 4 (`sku_recipe_mapping`) depends on step 2 (real POS) AND
  step 3 (modelled recipes). Halt for Adnan review before loading.
- Coverage gate: ≥75% POS revenue mapped before proceeding past step 4.
- Phase 3: OTS, SOY, DPI can be built without recipe coverage. CCC depends
  on COGS derivation. Sequence CCC last.
- Calibration step between Phase 3 and Phase 4: surface entity distributions;
  if all suppliers cluster in one tier, pause for manual threshold adjustment.

---

## 9. Code conventions

- Default to **no comments**. Only add comments where the WHY is non-obvious.
- Never write multi-paragraph docstrings; one short line max.
- Do not add backwards-compatibility shims, feature flags, or hypothetical
  future-proofing.
- Trust internal code and framework guarantees. Validate only at system
  boundaries (Railway feed, user input on Compose page).
- Don't introduce abstractions beyond what the task requires.
- Don't create new files unless the spec calls for them.
