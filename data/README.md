# Data directory

## Layout

- `seed/` — synthetic seed CSVs (modelled, except `07_pos_daily.csv` which is
  reference-only and not loaded). See `seed/README.md` for provenance and
  per-file notes.
- `load.py` — first-time bootstrap script. Pulls real POS from the Railway
  endpoint, loads seed CSVs, builds derived tables, writes `kfc.duckdb`.
- `kfc.duckdb` — the database. Generated; not committed.
- `sku_recipe_mapping_candidates.csv` — generated for human review.
  Not committed. See CLAUDE.md Section 1.

## Provenance summary

| Table                          | Ring     | Source                              |
| ------------------------------ | -------- | ----------------------------------- |
| `pos_transactions`             | observed | Railway feed                        |
| `pos_line_items`               | observed | Railway feed                        |
| `menu_items`                   | observed | derived from POS                    |
| `store_summary`                | observed | derived from POS + seed metadata    |
| `ingredient_consumption_daily` | derived  | POS x recipes                       |
| `margin_chain_per_sku`         | derived  | POS price - traced procurement cost |
| `supplier_exposure_per_sku`    | derived  | revenue x recipe x supplier         |
| `nodes`                        | modelled | `seed/01_nodes.csv`                 |
| `suppliers`                    | modelled | `seed/03_suppliers.csv`             |
| `ingredients`                  | modelled | `seed/04_ingredients.csv`           |
| `recipes`                      | modelled | `seed/06_recipes.csv`               |
| `purchase_orders`              | modelled | `seed/09_purchase_orders.csv`       |
| `deliveries`                   | modelled | `seed/10_deliveries.csv`            |
| `invoices`                     | modelled | `seed/11_invoices.csv`              |
| `payments`                     | modelled | `seed/12_payments.csv`              |
| `sku_recipe_mapping`           | derived  | fuzzy match + manual review         |
| `computations`                 | derived  | persisted by `backend/lineage.py`   |
| `computation_inputs`           | derived  | persisted by `backend/lineage.py`   |
| `user_entities`                | derived  | user-saved compositions             |
