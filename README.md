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
streamlit run app.py
```

The app self-bootstraps DuckDB on first launch from
`data/seed/pos_snapshot.json.gz` (9 MB, bundled in the repo). No network
access is required — Streamlit Cloud-ready.

To explicitly rebuild the DB outside of Streamlit:

```bash
python data/load.py            # offline: reads the bundled snapshot
python data/load.py --live     # re-pulls POS from Railway by paginating
                               # across store IDs and refreshes
                               # data/seed/pos_snapshot.json.gz
```

The Railway `/transactions` single-payload endpoint truncates
intermittently (`IncompleteRead` mid-stream), so `--live` paginates
`/transactions?store_id=XXXX` across 4-digit store IDs and rebuilds the
snapshot from the union.

### Streamlit Cloud

`app.py` is the entry point, `requirements.txt` lists all deps, and all
paths are repo-relative. On first request the app runs `data/load.py`
inline (shown as a "Bootstrapping…" spinner — ~30 s) and caches the
result via `@st.cache_resource` for the rest of the deployment's
lifetime.

### macOS PATH note

If `streamlit` isn't found after `pip install`, your user-site `bin/`
directory probably isn't on `PATH`. Either run it through Python:

```bash
python3 -m streamlit run app.py
```

…or add the user-site bin directory to your shell rc. With Homebrew Python:

```bash
echo 'export PATH="$(python3 -m site --user-base)/bin:$PATH"' >> ~/.zshrc
exec zsh
```

Same fix applies to `pytest` after `pip install -r requirements.txt`.

## Important framing

The numbers produced by this prototype are computed against substantially
synthetic data. They are directionally plausible but not actual reflections
of KFC Pakistan's operations. The point of this prototype is not the specific
numbers — it is the methodology that produces them.
