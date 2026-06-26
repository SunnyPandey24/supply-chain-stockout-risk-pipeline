# Power BI Build Guide — Stockout Risk Dashboard

Follow this in order. Total build time: ~25-30 minutes.

## 1. Import data
- Power BI Desktop → Get Data → Text/CSV → select `powerbi/model_output.csv`
- Optional, for richer drill-downs: also import `data/raw/products.csv` and
  `data/raw/suppliers.csv`, and relate them to `model_output` on `sku` and
  `supplier_id` respectively (Model view → drag to create relationships).
- Set `risk_tier` as a Text column, sort order: create a column
  `risk_tier_sort` (1=High, 2=Medium, 3=Low) via Power Query if you want
  High to always appear first in visuals.

## 2. Add the DAX measures
Paste every measure from `dax_measures.md` into the `model_output` table
(Home → New Measure).

## 3. Build the page — "Stockout Risk Overview"

**Top row — KPI cards (Card visual):**
- `[Total SKU-Warehouse Pairs]`
- `[High Risk Count]`
- `[High Risk %]` (format as percentage)
- `[Estimated Exposure ($)]` (format as currency)

**Row 2 — Risk distribution:**
- **Donut chart**: `risk_tier` (legend) × count of `sku` (values) — shows
  the High/Medium/Low split at a glance.
- **Bar chart**: `category` (axis) × `Avg Days of Supply by Category`
  (values) — sort ascending, add a constant reference line at the
  average `base_lead_time_days` so it's visually obvious which
  categories fall below their replenishment window.

**Row 3 — The actual deliverable: the action table.**
- **Table visual** with columns: `sku`, `product_name`, `warehouse_id`,
  `category`, `days_of_supply`, `base_lead_time_days`,
  `stockout_risk_score`, `risk_tier`, `recommended_action`.
- Filter the table to `risk_tier = "High"` by default using a **Slicer**
  on `risk_tier` (so the manager can also click to "Medium" or "Low" to
  expand the view) — set the slicer's default selection to High.
- Apply the `Risk Color` conditional formatting measure to the
  `risk_tier` column background (Format visual → Cell elements →
  Background color → Format by Field value → `Risk Color`).
- Sort the table by `stockout_risk_score` descending — highest risk on top.

**Row 4 — Supplier context (if you imported suppliers.csv):**
- **Bar chart**: `supplier_name` × average `reliability_score`, sorted
  ascending — surfaces unreliable suppliers driving risk independent of
  any single SKU.

## 4. Add a slicer panel
- `category` slicer
- `warehouse_id` slicer
- `risk_tier` slicer (mentioned above, can double as the main filter)

## 5. Title & polish
- Page title: "Stockout Risk Intelligence — Weekly Replenishment Review"
- Subtitle text box: "Updated from latest inventory snapshot. High-risk
  SKUs need a PO decision this week."
- Use a consistent color theme (View → Themes) — red/amber/green for
  risk tiers is the only color-coding that should carry meaning; keep
  everything else neutral.

## What this dashboard is FOR (say this in your interview)
This isn't a "look at my charts" dashboard — it answers one specific
question every week: **which SKUs need a purchase order decision right
now, and why.** The table is the deliverable; the KPI cards and charts
exist to justify and contextualize that table, not the other way around.
