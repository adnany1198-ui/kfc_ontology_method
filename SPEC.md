# KFC Ontology — Architectural Specification

**Version:** 0.1
**Status:** Draft for build
**Audience:** Engineering (Claude Code) + strategic reviewers (Ahsan)

> Binding resolutions to ambiguities in this document live in `CLAUDE.md`.
> Where this spec and `CLAUDE.md` disagree, `CLAUDE.md` wins.

---

## 0. Reading guide

This document specifies a system that turns operational data from KFC Pakistan into the data layer for credit product simulations. It is both a methodology argument (sections 1–2) and an engineering specification (sections 3–8).

If you are a strategic reviewer, read sections 1, 2, 7, and 8 — the conceptual frame, the methodology, the demo arc, and what's deliberately out of scope.

If you are building, read sections 3–6 in order. Each section depends on the previous one.

The build target is a Streamlit application that runs locally — `git clone`, `pip install`, `streamlit run app.py`. No deployment, no authentication, no public URL.

---

## 1. The core claim

This prototype explores whether operating businesses like KFC Pakistan can be modelled in a way that produces a different class of insight than what conventional analytics platforms generate — and whether those insights can serve as the data layer for new financial products.

The conventional framing of the problem is data fragmentation: POS lives in one system, procurement in another, commissary in another. Solutions like Dynamics 365 address this by integrating the sources into a unified data layer. This integration is genuinely valuable. But integration alone does not produce what this system attempts to produce.

The thing being attempted here is different. It is to model the operational system as a set of temporally-aligned streams that can be composed — meaning that events in one stream can be related to events in another stream at corresponding moments in time, and the relationships across streams themselves become queryable objects that persist, can be referenced, and can be composed further.

This system has three layers:

- **Data Layer** — observed real data, derived computations, and modelled synthetic flows, all temporally aligned, with provenance tagged on every value
- **Derived entities** — lineage-aware quantities computed from the data layer (e.g., supplier trust scores, working capital coefficients, demand predictability indices) that are stored and can be referenced by other computations
- **Credit products** — configurable templates that compose derived entities into financial instrument simulations

The proof of architecture is composability: every number is decomposable to its source events, and new derived entities and credit products can be constructed from existing primitives.

The strategic hypothesis being tested: if this works for KFC, the same methodology may transpose to other operating assets (InDrive, other QSRs, broader SME populations). The output, if proven, would be a credit underwriting layer that uses observed operational data — addressing a gap that integrated-data platforms do not directly address.

**Important framing note.** The numbers produced by this prototype are computed against substantially synthetic data. They are directionally plausible but not actual reflections of KFC Pakistan's operations. The point of this prototype is not the specific numbers — it is the methodology that produces them. When real procurement data eventually replaces the modelled layer, the same methodology produces real numbers with the same structure. The system is being designed so that data layer can be swapped without architectural changes.

---

## 2. The distinction this prototype attempts to demonstrate

The standard critique of operational analytics is data fragmentation. The standard solution is integration: ERPs like Dynamics 365 bring POS, procurement, commissary, and supplier data into one platform, and BI tools sit on top to produce dashboards and reports.

Integration is necessary but, this prototype hypothesises, not sufficient for the class of insight that supports credit-product construction. The reason is not that integrated data is incomplete. It is that the dominant query pattern over integrated data is still static retrieval and aggregation — pull values, sum them, render them. This pattern produces insights of a particular shape: counts, sums, averages, breakdowns, period-over-period comparisons. These are useful for operational reporting and management review.

The class of insight this prototype is attempting to produce has a different shape. It emerges from interrelations across temporally-aligned streams, where the answer to a question is not a value pulled from any single dataset but a structural pattern that becomes visible only when multiple streams are referenced against each other at corresponding moments.

Five examples of what is meant by this, illustrated against the prototype's data model:

**Example 1 — Per-SKU true margin including supplier-cost drift.** A standard BI query can return "gross margin on Zinger Burger" by subtracting average ingredient cost from price. But the actual margin on a specific Zinger sold on a specific Tuesday depends on which supplier's chicken was in inventory that day, what KFC paid that supplier for that batch, and how chicken commodity prices were drifting that week. This requires aligning POS, procurement-price history, and recipe BOM streams temporally to produce a per-transaction true margin trajectory. Static retrieval cannot produce this; it can only produce aggregate margin which masks the drift.

**Example 2 — Supplier reliability as a continuously-updating signal.** "Big Bird's on-time delivery rate" can be retrieved as a static number. But "Big Bird's on-time rate over the trailing 90 days, weighted by SKU revenue exposure, with the trend direction" is a derived quantity composed from delivery events, recipe relationships, and POS revenue, all temporally aligned. This composed quantity becomes the input to a credit-pricing decision. The composed quantity is not a row in any system — it exists only as the result of relating streams.

**Example 3 — Demand-driven supplier cashflow inference.** A supplier's own cashflow position can be inferred from the buyer's data: their outstanding receivables from KFC, derived from KFC's own invoice and payment streams, indicate when they are most cash-tight. This is not retrieved from any single source — it is computed by aligning KFC's procurement events against KFC's payment schedule and back-projecting onto the supplier. The supplier's financial state becomes visible from operational data, which is what enables a financial product.

**Example 4 — Promotion-supply chain alignment.** Whether the supply chain anticipated a promotional demand spike requires aligning the promotional calendar, the realised POS uplift, and the delivery schedule. Each lives in a separate domain. The insight ("Wednesday's Zinger promotion is driving demand 37% above average but chicken deliveries that day are 25% below the weekly mean") emerges only from temporal cross-reference. No single dashboard surfaces it because no single team owns the question.

**Example 5 — Working capital responsiveness to settlement rails.** The same operational data layer produces different working-capital-cycle values depending on how settlement happens (bank wire vs Raast vs stablecoin). The system can simulate the differential by holding the operational data layer constant and varying the settlement-friction parameter. This makes the value of programmable settlement directly quantifiable from operational data — which is the kind of insight that justifies infrastructure investment but is invisible to static reporting.

**The common pattern.** Each of these insights satisfies two conditions:

- **Cross-stream**: it requires referencing entities from multiple operational domains
- **Temporal**: the relationships must be aligned at corresponding moments — not aggregated across all time, but evaluated at a moment, with a trajectory through moments

The hypothesis being tested is that when these cross-stream temporal relationships are made queryable and persistent (as "derived entities" — see Section 4), they become the data layer for credit products that cannot easily be priced against retrieved-and-aggregated data.

**What the prototype does not claim.** This prototype does not claim that conventional analytics platforms cannot produce any of these insights with sufficient custom engineering. They likely can, with effort. The claim is that the architectural pattern — data layer as temporally-aligned streams, derived entities as persistent composable quantities, credit products as templates over those entities — makes this class of insight a standard output of the system, rather than something that requires bespoke construction each time.

Whether this architectural pattern delivers enough value to justify itself relative to extending existing platforms is exactly the question this prototype attempts to surface. It is not yet answered.

---

## 3. Data model

### 3.1 The three rings

Every table in the database is tagged with one of three provenance values:

- **observed** — real data, sourced from production systems (the KFC POS feed)
- **derived** — computed from observed data via a deterministic formula (e.g., ingredient consumption derived from POS × recipes)
- **modelled** — synthetic data structurally plausible but not anchored in real observation (e.g., supplier deliveries, since real receiving data is not currently captured)

Provenance is stored as a column on every fact table and as metadata on every derived value. The frontend exposes provenance as a coloured badge on every number.

### 3.2 Data Layer tables

**observed:**

```
pos_transactions          (real, 184k rows)
pos_line_items            (real, 339k rows)
menu_items                (real, 419 SKUs)
store_summary             (real, 34 stores)
```

**derived:**

```
ingredient_consumption_daily   (POS × recipes → ingredient flow per store per day)
margin_chain_per_sku           (POS price - traced procurement cost)
supplier_exposure_per_sku      (revenue attribution per supplier via recipes)
```

**modelled:**

```
nodes                     (commissary, warehouses — real entities, modelled flows)
suppliers                 (15 entities; Big Bird, K&N real; others synthetic placeholders)
ingredients               (33 raw materials)
recipes                   (SKU → ingredient BOM)
purchase_orders           (modelled cadence based on derived consumption)
deliveries                (modelled with realistic delay/quality variance)
invoices                  (linked to deliveries)
payments                  (linked to invoices)
```

### 3.3 Recipe mapping (the load-bearing bridge)

The real POS has 419 SKUs. The modelled supply chain has ~30 recipe templates. A mapping table connects them:

```
sku_recipe_mapping:
  pos_sku_id          (from menu_items, real)
  recipe_template_id  (from recipes, modelled)
  match_quality       (exact | close | approximate | unmapped)
  mapped_by           (system | manual)
  mapped_at           (timestamp)
```

SKUs without a recipe mapping appear in Ring 1 but do not propagate to Rings 2 and 3. This is acceptable and must be visible — the agent's answers should always indicate when a question's answer is incomplete due to unmapped SKUs.

### 3.4 The time cursor

The system maintains a virtual "current time" — a timestamp that all queries filter against. The default is the latest timestamp in the observed POS data. The user can move the cursor backward (or forward, up to the dataset's maximum) and all panels update against the cursor.

**Implementation:** every query that depends on time accepts an `at_time` parameter. Tables with event timestamps are filtered with `event_time <= at_time`. The cursor is stored in Streamlit session state.

This is what makes the system a "live operational flow" demonstration — not real-time data, but a replay of the dataset's time dimension that demonstrates the temporal architecture.

### 3.5 Lineage tables

Every derived value is computed by a function (a "computation") that has named inputs and produces a named output. Lineage is stored in two tables:

```
computations:
  computation_id          (uuid)
  entity_type             (e.g., 'ots_score', 'soy_value')
  entity_id               (e.g., supplier_id this computation produced a value for)
  computed_at             (timestamp of computation run)
  at_time                 (cursor time the computation was run against)
  formula_name            (e.g., 'ots_v1')
  formula_version         (semver)
  output_value            (numeric or json)

computation_inputs:
  computation_id          (fk -> computations)
  input_name              (e.g., 'on_time_rate')
  input_value             (numeric or json)
  source_table            (which table the input came from)
  source_filter           (the SQL filter that produced this input)
  source_row_count        (how many rows fed into this input)
```

Decomposition (the drill-down) is a recursive query: given a `computation_id`, return its inputs; for each input that itself was the output of a computation, recurse.

The terminal nodes of any decomposition are values from `observed` or `modelled` data layer tables — i.e., raw events.

### 3.6 User-constructed entities

The user can construct new derived entities by combining existing ones. These are stored as:

```
user_entities:
  user_entity_id          (uuid)
  name                    (user-provided)
  created_at              (timestamp)
  composition_spec        (json describing the composition)
```

`composition_spec` format:

```json
{
  "operation": "weighted_sum | threshold | trend_direction | rolling_average",
  "inputs": [{"entity_type": "ots_score", "weight": 0.6}],
  "params": {"threshold": 0.7, "window_days": 30}
}
```

User-constructed entities work the same way as built-in ones: they compute on the time cursor, store lineage, and can be referenced by credit product templates.

---

## 4. Computation model — derived entities

### 4.1 General pattern

Each derived entity is implemented as a Python module in `derived/` with this contract:

```python
def compute(entity_id: str, at_time: datetime, db: DuckDBConnection) -> ComputationResult:
    """
    Compute the entity value for a given target at a given time.
    Returns ComputationResult with:
      - value: the computed value
      - components: dict of named sub-values
      - inputs: dict of named inputs with source filters
      - formula_version: semver
    """
```

The function:

1. Queries the data layer for the inputs needed (filtered by `at_time`)
2. Computes the value using a documented formula
3. Returns a `ComputationResult` that captures the value, the components that composed it, and the inputs that fed the components
4. The caller persists the result into the `computations` and `computation_inputs` tables

Recomputation happens when the time cursor moves or when underlying data layer changes. For the v1 build, recomputation is on-demand (computed when the entity is queried) rather than scheduled.

### 4.2 OTS — Operational Trust Score

**Conceptual definition.** A per-supplier composite score (0.0 to 1.0) representing the supplier's operational reliability, weighted across multiple performance dimensions, computed from observed delivery and quality data.

**Inputs:**

- `on_time_rate` — % of deliveries arriving on or before `expected_delivery_date` (last 90 days at cursor)
- `fill_rate` — % of deliveries where `delivered_qty >= 0.95 × ordered_qty` (last 90 days)
- `quality_pass_rate` — `quality_pass_qty / delivered_qty`, averaged over last 90 days
- `volume_consistency` — `1 - (stddev/mean of weekly delivery volume over last 90 days)`
- `payment_compliance` — count of disputed invoices / total invoices (last 90 days)

**Formula:**

```
ots_score = (
    0.30 * on_time_rate +
    0.20 * fill_rate +
    0.25 * quality_pass_rate +
    0.15 * volume_consistency +
    0.10 * (1 - payment_compliance)
)
```

**Tier mapping:**

- A: >= 0.92
- B: 0.85 – 0.92
- C: 0.78 – 0.85
- D: < 0.78

**Output:**

```python
ComputationResult(
    value=0.83,
    components={
        "on_time_rate": 0.79,
        "fill_rate": 0.92,
        "quality_pass_rate": 0.99,
        "volume_consistency": 0.85,
        "payment_compliance": 0.02,
        "tier": "B"
    },
    inputs={...},  # SQL filters that produced each component
    formula_version="ots_v1.0.0"
)
```

### 4.3 SOY — Supplier Originatable Yield

**Conceptual definition.** The annualised yield available to the family office (or external investor) from financing a supplier's receivables, computed across the supplier's current outstanding invoices.

**Inputs (per supplier, at cursor):**

- `outstanding_invoices` — invoices issued but not yet paid, with amount and days-to-due
- `discount_rate` — discount applied to early payment (parameter, default 1.4% per cycle)
- `target_advance_lead` — days before due date when advance is offered (parameter, default 5)
- `default_risk_adjustment` — see CLAUDE.md for corrected formula

**Formula:**

```
For each outstanding invoice:
  duration_days = max(1, days_to_due - target_advance_lead)
  cycle_yield = discount_rate × invoice_amount
  annualised = cycle_yield × (365 / duration_days)
  risk_adjusted = annualised × risk_factor
soy_value = sum(risk_adjusted across invoices)
```

**Output:**

```python
ComputationResult(
    value=41_000_000,  # PKR per year originatable yield from this supplier
    components={
        "outstanding_amount": 418_000_000,
        "avg_days_to_due": 27,
        "n_invoices": 1206,
        "gross_annualised_yield_pct": 18.9,
        "risk_adjusted_yield_pct": 17.9
    },
    inputs={...}
)
```

### 4.4 CCC — Cash Conversion Coefficient

**Conceptual definition.** The system-wide working capital cycle: average days from POS event to cash freed of supplier obligations, weighted by margin.

**Inputs (system-wide, at cursor):**

- `pos_revenue_by_day` — daily POS revenue
- `cogs_by_day` — derived ingredient consumption × procurement prices
- `payment_terms_weighted_avg` — across all suppliers, weighted by their share of COGS
- `settlement_latency` — parameter, default 3 days (bank rails), 0 (stablecoin)
- `processing_overhead` — parameter, default 2 days (bank rails), 0 (stablecoin)

**Formula:**

```
effective_payment_cycle = payment_terms_weighted_avg + settlement_latency + processing_overhead

For a representative PKR 100 of revenue today:
  cogs = 100 × cogs_ratio
  margin = 100 - cogs
  obligation_clear_day = effective_payment_cycle
  margin_realised_day = 0  (cash collected immediately)
  float_days = effective_payment_cycle

ccc_days = effective_payment_cycle
deployable_float = (daily_cogs × effective_payment_cycle)
```

**Output:**

```python
ComputationResult(
    value=35,  # days
    components={
        "payment_terms_weighted_avg": 30,
        "settlement_latency": 3,
        "processing_overhead": 2,
        "deployable_float_pkr": 1_100_000_000,
        "daily_cogs_pkr": 31_000_000
    },
    inputs={...}
)
```

CCC is parameter-sensitive — the settlement rail (bank vs stablecoin) directly changes the value. This is the entity the credit product simulator uses to demonstrate the stablecoin value capture.

### 4.5 DPI — Demand Predictability Index

**Conceptual definition.** A per-supplier measure of how accurately the system can forecast that supplier's order volume at 30/60/90 day horizons.

**Inputs (per supplier, at cursor):**

- `historical_orders` — POs issued to this supplier over the past 12 months
- `forecast_methodology` — simple moving average of past 30/60/90 day demand (v1; can be replaced with sophisticated forecaster later)
- `actual_demand` — actual order volume realised in past horizons

**Formula:**

```
For each historical forecast horizon (30, 60, 90 days):
  forecast_at_t = mean(historical_orders[t-30:t])
  actual_at_t_plus_h = sum(orders[t:t+h])
  forecast_error = abs(forecast_at_t × h_scaling - actual_at_t_plus_h)
  forecast_error_pct = forecast_error / actual_at_t_plus_h

dpi_at_horizon_h = 1 - mean(forecast_error_pct across windows)
dpi_score = weighted_avg(dpi_30, dpi_60, dpi_90)
```

**Output:**

```python
ComputationResult(
    value=0.81,  # 0-1, higher = more predictable
    components={
        "dpi_30": 0.88,
        "dpi_60": 0.81,
        "dpi_90": 0.74,
        "forecast_method": "sma_30"
    },
    inputs={...}
)
```

---

## 5. Credit product templates

A credit product template is a Python module in `products/` that consumes derived entities and produces a financial outcome simulation.

### 5.1 Common contract

```python
def simulate(parameters: dict, at_time: datetime, db: DuckDBConnection) -> ProductSimulation:
    """
    Simulate the credit product at the given time with the given parameters.
    Returns ProductSimulation with:
      - eligible_targets: list of suppliers/entities that qualify
      - aggregate_metrics: dict (e.g., total_yield, total_deployment, weighted_avg_rate)
      - per_target_outcomes: list of per-supplier outcomes
      - parameter_traces: which derived entities were consulted with which values
    """
```

### 5.2 Product 1: Captive Invoice Financing

**Concept.** The family office advances early payment on supplier invoices in exchange for a discount, scoring eligibility and pricing via OTS.

**Parameters:**

- `ots_threshold` (default 0.78): minimum OTS for eligibility
- `discount_rate_by_tier` (default `{A: 0.009, B: 0.013, C: 0.017, D: blocked}`): per-cycle discount
- `advance_lead_days` (default 5): days before due date payment is advanced
- `max_deployment_pkr` (default unlimited): cap on total capital deployed

**Eligibility:**

- Supplier has OTS >= `ots_threshold`
- Supplier has outstanding invoices at the cursor time

**Computation:**

```
For each eligible supplier:
  pull OTS (cached or recompute at cursor)
  pull outstanding invoices
  apply discount_rate_by_tier[supplier_tier] to each invoice
  sum annualised yield contribution

aggregate:
  total_eligible_outstanding = sum across suppliers
  total_yield_annualised = sum of per-supplier yield
  weighted_avg_rate = yield / outstanding × (365 / avg_duration)
```

**Output (example):**

```
eligible_suppliers: 12 / 15
total_outstanding: PKR 752M
total_yield_annualised: PKR 132M
weighted_avg_rate: 17.5%
excluded_suppliers: 3 (1 below threshold, 2 no outstanding invoices)
```

### 5.3 Product 2: Forward / Pre-Invoice Credit

**Concept.** The family office offers credit lines to suppliers based on forecasted future purchase orders (not yet issued), priced against DPI.

**Parameters:**

- `dpi_threshold` (default 0.70): minimum DPI for eligibility
- `commitment_horizon_days` (default 90): how far forward demand is forecasted
- `advance_ratio` (default 0.40): fraction of forecasted PO value offered as credit line
- `discount_rate_by_dpi_band` (default `{>0.85: 0.012, 0.75-0.85: 0.016, 0.70-0.75: 0.020}`): rate by predictability band
- `max_deployment_pkr` (default unlimited)

**Eligibility:**

- Supplier has DPI >= `dpi_threshold`
- Forecasted demand over `commitment_horizon_days` > 0

**Computation:**

```
For each eligible supplier:
  pull DPI
  forecast PO volume over commitment_horizon_days (using same forecast method as DPI)
  credit_line_offered = forecast × advance_ratio
  effective_rate = discount_rate_by_dpi_band[supplier_dpi_band]
  annualised_yield = credit_line × effective_rate × (365 / avg_duration)

aggregate:
  total_credit_committed = sum across suppliers
  expected_drawdown_rate = (parameter, default 0.65 — fraction of line actually used)
  total_deployment = total_credit_committed × expected_drawdown_rate
  total_yield_annualised = sum of per-supplier yield
```

### 5.4 Product 3: Securitised Yield Originator

**Concept.** Package SOY across the supplier base as a tradeable yield product. The family office originates the receivables, takes an origination fee, and sells the yield stream to external investors.

**Parameters:**

- `ots_threshold` (default 0.78): minimum OTS for inclusion in the pool
- `pool_target_size_pkr` (default 500M): target size of yield pool
- `origination_fee_bps` (default 50): basis points retained by originator
- `target_investor_yield_pct` (default 12.0): annualised yield offered to investors
- `concentration_limit_pct` (default 25): max % of pool from any single supplier
- `settlement_rail` (default "bank"): "bank" | "raast" | "stablecoin"

**Computation:**

```
Build pool:
  rank eligible suppliers by SOY
  fill pool up to pool_target_size_pkr, respecting concentration_limit_pct
  compute pool_gross_yield = sum(SOY for included suppliers)

Originator economics:
  origination_fee = pool_size × origination_fee_bps / 10000
  investor_yield_paid = pool_size × target_investor_yield_pct / 100
  retained_spread = pool_gross_yield - investor_yield_paid

Settlement rail impact (uses CCC):
  bank: ccc_days = 35, effective yield reduced by friction
  stablecoin: ccc_days = 30, full programmable yield captured

aggregate:
  pool_size, n_suppliers_included, gross_yield, originator_revenue (fee + spread),
  investor_yield_paid, settlement_rail_value (delta between rails)
```

This product specifically demonstrates the value of stablecoin rails by showing the yield difference between settlement options.

---

## 6. API surface

The frontend consumes a single backend module: `backend/api.py`. Functions:

### 6.1 Time and data layer

```python
get_cursor() -> datetime
set_cursor(at_time: datetime) -> None
get_data_layer_summary(at_time: datetime) -> dict
# Returns: {real_pos_txns_today, derived_consumption_volume, modelled_ap_outstanding, etc.}
query_data_layer(table: str, filter: dict, at_time: datetime, limit: int) -> DataFrame
```

### 6.2 Derived entities

```python
list_entities(entity_type: str) -> list[str]
# e.g., list_entities('ots') returns all supplier IDs

get_entity(entity_type: str, entity_id: str, at_time: datetime) -> ComputationResult
# Returns the entity value at the given time, computing it if not cached

get_entity_history(entity_type: str, entity_id: str, from_time: datetime, to_time: datetime, granularity: str) -> DataFrame
# For time-series sparklines

decompose(computation_id: str, depth: int = 1) -> dict
# Returns the immediate inputs of the computation, with each input flagged as
# either a 'leaf' (data layer event) or 'computation' (another computation_id to recurse into)
```

### 6.3 User-constructed entities

```python
construct_entity(name: str, composition_spec: dict) -> str
# Validates the spec, persists to user_entities table, returns user_entity_id

list_user_entities() -> list[dict]
delete_user_entity(user_entity_id: str) -> None
compute_user_entity(user_entity_id: str, target_id: str, at_time: datetime) -> ComputationResult
```

### 6.4 Credit products

```python
list_products() -> list[dict]
# Returns product templates with their parameter schemas
simulate_product(product_id: str, parameters: dict, at_time: datetime) -> ProductSimulation
get_product_default_parameters(product_id: str) -> dict
```

### 6.5 Provenance

```python
get_provenance(table: str) -> str  # 'observed' | 'derived' | 'modelled'
get_provenance_summary() -> dict
# System-wide breakdown of what % of values shown are observed/derived/modelled
```

---

## 7. Frontend specification

### 7.1 Layout

Streamlit multi-page app. Single shared sidebar with the time cursor (a date slider) and a provenance-summary indicator (small panel showing % observed/derived/modelled).

Pages (in sidebar nav order):

1. **Overview** — architecture diagram, core claim, navigation hints
2. **Data Layer** — real-time view of data layer at current cursor
3. **Derived Entities** — OTS, SOY, CCC, DPI panels
4. **Credit Products** — three product simulators
5. **Compose** — user-constructed entities builder
6. **Drill-down** — guided composability demonstration
7. **About** — what's synthetic, what's real, methodology brief

### 7.2 Data Layer page

Three columns side by side, each headed by a coloured provenance badge:

**OBSERVED (green badge): Real POS panel**

- Transactions today (count, value)
- Top 5 stores by revenue today
- Channel mix
- SKU mix top 10

**DERIVED (yellow badge): Computed flow panel**

- Top ingredients consumed today (from POS × recipes)
- Per-store ingredient demand attribution
- Margin chain top 10 SKUs

**MODELLED (orange badge): Synthetic supply chain panel**

- POs issued today
- Deliveries received today
- Invoices outstanding
- Payments due in next 7 days

All panels filter on the time cursor. Moving the cursor updates everything.

### 7.3 Derived entities page

Four sections, one per entity type. Each section has:

- Summary row: aggregate or distribution at cursor
- Per-target table: one row per supplier/entity with: value, tier (if applicable), component sparklines, last-updated timestamp
- Click any row → entity detail panel: shows components with sparkline trends, formula, "decompose" button

**OTS section example:**

```
[OTS Distribution: A=4, B=8, C=2, D=1] [Cursor: 2025-06-15]

Supplier              | OTS  | Tier | 30d Trend | Components Preview
Big Bird Foods        | 0.83 |  B   | -----     | OT:79% Fill:92% Q:99%
K&N's Foods           | 0.79 |  C   | -----     | OT:77% Fill:95% Q:99%
National Spice        | 0.94 |  A   | -----     | OT:93% Fill:81% Q:100%
...
[Click any row to see full breakdown]
```

### 7.4 Credit products page

Three tabs, one per product. Each tab has:

**Left column — Parameters:**

- Sliders/inputs for each parameter
- "Reset to defaults" button
- "Save scenario" (optional, v2)

**Center column — Output:**

- Aggregate metrics (total yield, deployment, eligible count)
- Per-supplier outcomes table
- Charts: yield contribution by supplier, eligibility breakdown

**Right column — Lineage:**

- "Which derived entities are being used?" (OTS, DPI, etc with their values)
- "Click to decompose" → opens drill-down for that entity

For the Securitised Yield Originator specifically, include a settlement rail comparison widget:

```
Settlement rail:  [Bank v]   [Raast]   [Stablecoin]
           Bank          Raast        Stablecoin
CCC days   35            32           30
Pool yield 130M          145M         158M
Friction   28M           13M          0M
```

### 7.5 Compose page

Form-based UI for building a new derived entity:

- Name (text input)
- Operation (dropdown: Weighted Sum | Threshold | Trend Direction | Rolling Average)
- Inputs (multi-select from existing entity types; for weighted sum, weights for each)
- Parameters (varies by operation; e.g., threshold value, window length)
- Preview — shows the entity computed at cursor for a sample target
- Save — persists to `user_entities` table

After saving, the user-constructed entity becomes selectable in the credit product score-input dropdowns. This is the constructive composability demonstration.

### 7.6 Drill-down page

A guided demonstration that walks through one full decomposition. Deterministic representative supplier (Big Bird Foods) — values computed live, walk path hardcoded.

Example walk:

1. "Captive Invoice Financing yield: PKR 132M"
   → Click "Decompose"
2. "Composed of 12 eligible suppliers. Top contributor: Big Bird PKR 41M"
   → Click "Decompose Big Bird"
3. "Computed from OTS 0.83, outstanding invoices PKR 418M, 27 days avg duration"
   → Click "Decompose OTS"
4. "OTS 0.83 = 0.30 × 0.79 (OT) + 0.20 × 0.92 (Fill) + 0.25 × 0.99 (Q) + ..."
   → Click "Decompose On-Time Rate"
5. "Computed from 1,206 delivery events. 953 on-time, 207 late, 46 very late"
   → Click "Show delivery events"
   → Table of actual delivery events at Ring 3 (modelled).

At every step, the provenance badge shows what ring the data lives in. The terminal node is always either an observed event (real POS) or a modelled event (synthetic delivery).

### 7.7 Overview page

A simple architecture diagram (rendered as ASCII or a static image), the core claim, three quick-jump buttons:

- "See the data layer" → Data Layer page
- "See derived entities" → Derived Entities page
- "Simulate a credit product" → Credit Products page

Plus a notable-numbers band at the bottom showing current key metrics at cursor.

### 7.8 About page

- **What this prototype is testing:** a brief restatement of the core claim (sections 1–2), framed as hypothesis rather than assertion
- **What's real vs synthetic:** table-by-table provenance — what is observed (real POS), what is derived (computed from observed), what is modelled (synthetic flows). Specific tables and row counts.
- **The five example insights** (from Section 2) re-rendered as a short narrative — each one with a "see this in the tool" link to the relevant page
- **What this is not claiming:** clear statement that the numbers are synthetic and the methodology is what's being tested
- **What data would convert modelled to observed:** a list of specific data acquisitions (real receiving logs, real invoice records, real supplier delivery confirmations) that would replace modelled tables with observed ones
- **Known limitations and gaps:** SKU mapping coverage, computation performance, forecast methodology simplicity, etc.

---

## 8. Repository structure

```
kfc-ontology-methodology/
|-- README.md                     # 1-page core claim + how to run
|-- SPEC.md                       # this document
|-- METHODOLOGY.md                # sections 1-2 rewritten for strategic readers
|-- CLAUDE.md                     # agent brief (binding resolutions live here)
|-- requirements.txt
|-- app.py                        # Streamlit entry point (Overview page)
|-- pages/                        # Streamlit pages
|   |-- 01_Data_Layer.py
|   |-- 02_Derived_Entities.py
|   |-- 03_Credit_Products.py
|   |-- 04_Compose.py
|   |-- 05_Drill_Down.py
|   |-- 06_About.py
|-- backend/
|   |-- api.py                    # API surface (section 6)
|   |-- db.py                     # DuckDB connection management
|   |-- cursor.py                 # Time cursor state
|   |-- lineage.py                # Lineage tracking utilities
|-- derived/                      # Derived entity computations
|   |-- base.py                   # ComputationResult, common patterns
|   |-- ots.py
|   |-- soy.py
|   |-- ccc.py
|   |-- dpi.py
|   |-- user_entities.py          # User-constructed entity runtime
|-- products/                     # Credit product templates
|   |-- base.py                   # ProductSimulation, common patterns
|   |-- captive_invoice_financing.py
|   |-- forward_credit.py
|   |-- securitised_yield_originator.py
|-- data/
|   |-- README.md                 # Provenance documentation
|   |-- kfc.duckdb                # Generated by load.py
|   |-- seed/                     # Seed CSVs for synthetic generation
|   |-- load.py                   # Bootstrap script
|-- scripts/
|   |-- generate_synthetic.py     # Regenerate modelled data from seeds
|   |-- load_real_pos.py          # Load real POS data
|   |-- compute_all_recipes.py    # Build sku_recipe_mapping table
|   |-- precompute_entities.py    # Optionally precompute derived entities
|-- components/                   # Reusable Streamlit components
|   |-- provenance_badge.py
|   |-- drill_panel.py
|   |-- entity_card.py
|   |-- time_cursor_widget.py
|-- tests/
    |-- test_derived_entities.py
    |-- test_lineage.py
    |-- test_products.py
```

---

## 9. Build sequence

Strict order. Each step depends on the previous.

**Phase 1: Data Layer (target: 2-3 days of Claude Code time)**

1. Set up project skeleton (requirements.txt, app.py, basic Streamlit shell)
2. Load real POS into DuckDB
3. Load modelled supply chain (already generated CSVs from previous work) into DuckDB
4. Build `sku_recipe_mapping` table — semi-automated mapping with manual review (depends on steps 2 and 3)
5. Build the derived consumption table (POS × recipes)
6. Implement time cursor (sidebar widget + session state)
7. Build provenance tagging on all tables
8. Build Data Layer page

**Phase 2: Lineage infrastructure (1-2 days)**
9. Create `computations` and `computation_inputs` tables
10. Implement `ComputationResult` base class
11. Implement `decompose()` API
12. Add unit tests

**Phase 3: Derived entities (3-4 days)**
13. Implement OTS — first entity, sets the pattern
14. Implement SOY
15. Implement DPI
16. Implement CCC (last — depends on recipe coverage; falls back to industry default if <75%)
17. Calibration step: surface entity distributions; pause if all suppliers cluster in one tier
18. Build Derived Entities page

**Phase 4: Credit products (3-4 days)**
19. Implement Captive Invoice Financing
20. Implement Forward Credit
21. Implement Securitised Yield Originator
22. Build Credit Products page with three tabs

**Phase 5: Composability (2-3 days)**
23. Implement user-constructed entity model
24. Build Compose page
25. Wire user entities into credit product score-input dropdowns

**Phase 6: Drill-down and polish (2 days)**
26. Build Drill-down page (the guided demonstration with Big Bird as representative)
27. Build Overview and About pages
28. Write README.md, METHODOLOGY.md, CLAUDE.md
29. End-to-end test of demo arc

**Total estimate:** 13-18 days of Claude Code-assisted work. If you (Adnan) are reviewing tightly and Claude Code is doing the bulk of the implementation, ~2-3 weeks calendar time.

---

## 10. Out of scope for v1

- Real-time data refresh (snapshot only, cursor replays)
- Authentication / multi-user (runs locally for single user)
- Public deployment (local-only via `streamlit run`)
- Custom dashboards / saved views
- Agent chat integration in the UI (the underlying agent from the existing build can remain a separate CLI tool)
- Mobile / responsive design (desktop only, large viewport)
- Internationalisation
- Database migration tooling (DuckDB is regenerated from scripts)
- Comprehensive error handling for malformed user-constructed entities (basic validation only)
- Production-grade logging or monitoring
- Performance optimisation beyond functional acceptability
- Regeneration of modelled supply chain against real POS demand (deferred to v1.5)
- System-wide user entities (only target-scoped in v1)

These are deferred to v2 if/when the v1 demonstration warrants further investment.

---

## 11. Success criteria for v1

The build is complete when:

1. Ahsan can clone the repo, run `pip install -r requirements.txt && python data/load.py && streamlit run app.py`, and have a working application open in his browser.
2. He can scrub the time cursor and see all panels update coherently.
3. He can navigate to the Derived Entities page, see OTS scores for all suppliers, click any supplier, see its components, click "decompose" and walk all the way down to specific delivery events.
4. He can navigate to the Credit Products page, simulate captive invoice financing with default parameters, see the yield output, change the OTS threshold, see the yield recompute, and trace back through the lineage to see which suppliers' OTS values drove the change.
5. He can navigate to the Compose page, build a new entity (e.g., "60% OTS + 40% DPI, threshold at 0.75"), save it, and select it as the score input in a credit product dropdown.
6. He can navigate to the Securitised Yield Originator product, toggle between settlement rails, and see the yield difference attributable to programmable settlement.
7. The provenance of every value shown is visible and accurate — no synthetic value is presented as real.

If these seven conditions are met, the methodology is demonstrated. The numbers being synthetic does not matter. The structure being walkable, composable, and inspectable is what matters.

---

## 12. Notes on the strategic claim

This v1 build proves the methodology end-to-end for KFC Pakistan. The strategic claim it enables is:

The same methodology — data layer, derived entities, credit product templates, composability, time-cursor flow — transposes directly to other operating assets. InDrive's drivers become the underwriting targets. Trips become the data layer events. Driver OTS, driver DPI, fleet-level CCC and SOY become the derived entities. Forward earnings credit, performance-linked rates, and securitised driver-receivables become the credit products. The architecture does not change. The instance changes.

A second deployment against a meaningfully different operating asset (InDrive) is the proof point that this is methodology, not a one-off build. That is the strategic ambition this v1 sets up.

---

*End of specification.*
