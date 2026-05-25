# KFC Ontology Method

A prototype that turns KFC Pakistan operational data into the data layer for
credit product simulations.

The system has three layers:

1. **Data Layer** — temporally-aligned streams from POS, procurement, and
   commissary operations, with every value tagged as `observed`, `derived`,
   or `modelled`.
2. **Derived entities** — lineage-aware quantities computed from the data
   layer (supplier trust scores, working-capital coefficients, demand
   predictability), stored and composable.
3. **Credit products** — configurable templates that compose derived entities
   into financial-instrument simulations (invoice financing, forward credit,
   securitised yield).

The proof of architecture is composability: every number decomposes to its
source events, and new derived entities and credit products can be
constructed from existing primitives.

See [`METHODOLOGY.md`](METHODOLOGY.md) for the strategic frame and
[`SPEC.md`](SPEC.md) for the engineering specification.
[`CLAUDE.md`](CLAUDE.md) holds binding resolutions to spec ambiguities.

## Status

Pre-build scaffold. Phase 1 (Data Layer) has not started.

## How to run (once built)

```bash
git clone <repo>
cd kfc_ontology_method
pip install -r requirements.txt
python data/load.py        # first-time setup: pulls real POS, builds DuckDB
streamlit run app.py
```

## Important framing

The numbers produced by this prototype are computed against substantially
synthetic data. They are directionally plausible but not actual reflections
of KFC Pakistan's operations. The point of this prototype is not the specific
numbers — it is the methodology that produces them.
