# Proposed SPEC.md patch — §3.3 one-to-many mapping schema

Not applied. Awaiting Adnan's sign-off.

## Background

CLAUDE.md §1 already documents the 1:many override as a binding
resolution. The proposal below brings SPEC.md §3.3 in line with the
implemented shape so the spec and the build agree.

## Patch (unified diff against SPEC.md §3.3)

```diff
--- SPEC.md
+++ SPEC.md
@@ §3.3
 ### 3.3 Recipe mapping (the load-bearing bridge)

-The real POS has 419 SKUs. The modelled supply chain has ~30 recipe templates. A mapping table connects them:
+The real POS has ~420 SKUs (varies as new products are received from
+the feed). The modelled supply chain has 31 recipe templates. A mapping
+table connects them. Because real POS items are routinely **bundles**
+(`XTREME DUO BOX (2 ZIN+2H&C+1LF+2RD)` is five distinct constituents),
+a 1:1 collapse would produce systematically wrong margin and
+consumption numbers for ~75% of revenue. The table is therefore
+one-to-many: one row per `(real_sku_id, recipe_template_id)` pair, with
+an explicit `quantity` multiplier expressing how many template units a
+single real-SKU sale consumes.

 ```
 sku_recipe_mapping:
-  pos_sku_id          (from menu_items, real)
-  recipe_template_id  (from recipes, modelled)
-  match_quality       (exact | close | approximate | unmapped)
-  mapped_by           (system | manual)
-  mapped_at           (timestamp)
+  real_sku_id          (pos product_id from menu_items)
+  recipe_template_id   (skus.sku_id, or an ING-... ingredient for
+                        direct-ingredient bundle constituents like dip
+                        sachets / cheese slices that have no recipe)
+  quantity             (recipe template units per real-SKU sale)
+  confidence_band      (exact | close | approximate |
+                        composite_decomposed | composite_partial |
+                        needs_manual_decomposition | unmapped |
+                        exclude_wastage)
+  component_role       (primary | constituent)
+  note                 (parser provenance, free-form)
+  approved_by_reviewer (bool)
+  mapped_by            (system | manual)
+  mapped_at            (timestamp)
 ```

-SKUs without a recipe mapping appear in Ring 1 but do not propagate to Rings 2 and 3. This is acceptable and must be visible — the agent's answers should always indicate when a question's answer is incomplete due to unmapped SKUs.
+SKUs without a recipe mapping appear in Ring 1 but do not propagate to
+Rings 2 and 3. This is acceptable and must be visible — the agent's
+answers should always indicate when a question's answer is incomplete
+due to unmapped SKUs. At v1 build time, recipe coverage is **99.23% of
+POS revenue** by this scheme.
+
+**Direct-ingredient targets.** Where a bundle constituent has no recipe
+template but maps cleanly to a single ingredient (e.g. `DIP` →
+`ING-081` hot sauce sachet; `SLICE` → `ING-050` cheese slice), the row
+carries the `ING-` identifier in `recipe_template_id`. The derived
+`ingredient_consumption_daily` table understands the prefix and routes
+the quantity straight to the ingredient, skipping the recipe BOM lookup.
```

## Why this rises to a spec change rather than a CLAUDE.md note

§3.3 is consulted by anyone reading the spec to understand what the
mapping table looks like. A reader who only sees the 1:1 schema there
will write join logic that silently truncates ~75% of revenue. Bringing
the spec in line with the implementation removes the trap.

## Cross-references that also need a touch (smaller)

- §3.2 lists `menu_items (real, 419 SKUs)`. Real POS at v1 build time
  has 420 distinct product_ids after the quality filter; one is a known
  outlier with two names. Worth softening to "~420".
- §4 doesn't reference the mapping directly, but §4.4 (CCC) does
  depend on the coverage gate already documented in CLAUDE.md §11.
