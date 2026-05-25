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

v1 end-to-end build complete (Phases 1–6). Six pages, four derived
entities (OTS, SOY, DPI, CCC), three credit products, user-constructed
entities, drill-down on Big Bird, lineage decomposition, time cursor.

## How to run

```bash
git clone <repo>
cd kfc_ontology_method
pip install -r requirements.txt
python data/load.py        # pulls real POS from Railway, loads modelled
                           # supply chain, loads recipe mapping, derives
                           # ingredient consumption — ~30s end-to-end
streamlit run app.py
```

The bootstrap caches the POS payload in `data/raw_pos_cache/` (gitignored,
~275 MB) so subsequent loads skip the network round-trip.

## Important framing

The numbers produced by this prototype are computed against substantially
synthetic data. They are directionally plausible but not actual reflections
of KFC Pakistan's operations. The point of this prototype is not the specific
numbers — it is the methodology that produces them.
