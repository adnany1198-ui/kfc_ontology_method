# KFC Ontology — Synthetic Data Bundle

This bundle contains the synthetic seed data for the KFC Ontology project.
Place all CSVs in `data/seed/` in the project repo.

## Provenance

All files in this bundle are **modelled** (synthetic) data, except where noted.
The real POS data is pulled separately from the Railway receiver — see SPEC.md
Section 3.2 and the existing project at `/Users/adnzn1198/kfc-ai-prototype/scripts/01_pull_pos.py`.

## File index

| File | Rows | Provenance | Notes |
|------|------|------------|-------|
| 01_nodes.csv | 3 | modelled | Commissary, cold warehouse, dry warehouse (all Karachi) |
| 02_stores.csv | 151 | modelled | Store master across Pakistan. Real KFC PK has ~150 stores. *Real POS has 34 stores; reconcile per SPEC Section 3.2.* |
| 03_suppliers.csv | 15 | mixed | Big Bird Foods and K&N's Foods are real entities; others are realistic synthetic placeholders |
| 04_ingredients.csv | 33 | modelled | Chicken cuts, marinade, oil, vegetables, dairy, frozen, beverages, packaging |
| 05_skus.csv | 31 | modelled | Menu items with prices and categories |
| 06_recipes.csv | 166 | modelled | SKU → ingredient BOM mapping; the load-bearing bridge for cross-stream traversal |
| 07_pos_daily.csv | 844,141 | modelled | 6 months of synthetic POS — **do not use, replaced by real POS from Railway** |
| 08_ingredient_consumption_daily.csv | 847,131 | derived | Derived from 07 × 06. Will be regenerated from real POS × recipes |
| 09_purchase_orders.csv | 2,320 | modelled | POs generated from synthetic consumption with realistic supplier cadence |
| 10_deliveries.csv | 2,291 | modelled | Delivery events with realistic on-time/late/quality variance |
| 11_invoices.csv | 2,291 | modelled | Linked to deliveries |
| 12_payments.csv | 2,291 | modelled | Linked to invoices with realistic payment timing variance |

## Important notes for the build

1. **07_pos_daily.csv is not used in v1.** The real POS pulled from Railway replaces it. It's included here only as a reference for what the synthetic stream looked like.

2. **08 must be regenerated from real POS.** The ingredient consumption table should be computed from real POS × recipes, not from synthetic POS. Use the existing CSV only as a schema reference.

3. **09-12 are the modelled supply chain layer.** They need to be regenerated against real POS demand patterns in Phase 1 of the build, so the procurement flow actually reflects real consumption patterns rather than synthetic ones. See SPEC.md Section 3.2 for the integration approach.

4. **Store reconciliation needed.** Synthetic data has 151 stores; real POS has 34. Per SPEC.md, the build operates on real stores only — synthetic stores beyond the real 34 should be dropped or reframed clearly.

5. **Recipe mapping required.** Real POS has 419 SKUs; synthetic has 31 recipe templates. The `sku_recipe_mapping` table (SPEC.md Section 3.3) must be built to bridge them.

## Data calibration

- System revenue annualised: ~PKR 25.3B (target was 25-30B for KFC PK)
- Procurement as % of revenue: 42.5%
- Chicken price volatility through Jan-Jun 2025: PKR 280-600/kg (matches real 2025 patterns)
- Big Bird and K&N: real entities, both Lahore-based, deliver to Karachi commissary

## Regeneration

If these CSVs are lost or need to be regenerated with different parameters, the
build scripts that produced them are documented in the conversation history. The
key parameters:
- 6 month time horizon (Jan-Jun 2025)
- Ramadan: March 1 - March 30, 2025
- Eid: March 31 - April 2, 2025
- Day-of-week patterns: Fri/Sat peak (+30-35%), Sun strong (+20%), Mon/Tue weakest (-10-15%)
- Chicken supplier price drift: +17-19% Jan to March (Ramadan demand surge)
