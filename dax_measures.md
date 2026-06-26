# DAX Measures — Stockout Risk Dashboard

Import `model_output.csv` (and optionally `data/raw/products.csv`,
`suppliers.csv` for richer drill-downs) into Power BI, then create these
measures. Paste them as-is into a new Measure in Power BI Desktop.

## KPI Card Measures

```dax
Total SKU-Warehouse Pairs =
COUNTROWS(model_output)
```

```dax
High Risk Count =
CALCULATE(
    COUNTROWS(model_output),
    model_output[risk_tier] = "High"
)
```

```dax
High Risk % =
DIVIDE([High Risk Count], [Total SKU-Warehouse Pairs], 0)
```

```dax
Avg Risk Score =
AVERAGE(model_output[stockout_risk_score])
```

```dax
Estimated Exposure ($) =
SUMX(
    FILTER(model_output, model_output[risk_tier] = "High"),
    model_output[unit_cost] * model_output[avg_sales_7d] * model_output[base_lead_time_days]
)
```
*(This estimates the $ value of demand that could go unfulfilled if a High-risk
SKU stocks out for its full lead-time window — a business-translatable number,
not just a risk score.)*

## Conditional formatting helper (for table visuals)

```dax
Risk Color =
SWITCH(
    TRUE(),
    model_output[risk_tier] = "High", "#D9534F",
    model_output[risk_tier] = "Medium", "#F0AD4E",
    "#5CB85C"
)
```
Apply this as a **Conditional Formatting → Background Color → Field Value**
rule pointing at this measure, on the `risk_tier` column in your watchlist table.

## Days of Supply vs Lead Time gap (a derived risk indicator)

```dax
Supply Gap (days) =
AVERAGE(model_output[days_of_supply]) - AVERAGE(model_output[base_lead_time_days])
```
Negative = stock will likely run out before a reorder placed today would arrive.

## Category-level rollup

```dax
Avg Days of Supply by Category =
CALCULATE(
    AVERAGE(model_output[days_of_supply]),
    ALLEXCEPT(model_output, model_output[category])
)
```
