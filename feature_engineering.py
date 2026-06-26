"""
Builds the modeling dataset for the stockout-risk classifier.

For every (sku, warehouse) pair, takes a snapshot every 7 days (to avoid
near-duplicate rows from day-to-day autocorrelation) and computes:
  - trailing 7d / 30d average daily sales, 30d demand volatility
  - current on-hand / on-order quantity, days-of-supply
  - supplier lead time + reliability
  - LABEL: will this SKU/warehouse stock out at any point in the next
    14 days? (computed strictly from FUTURE data, never the snapshot day
    itself, to avoid leakage)

Output: data/processed/model_features.csv
"""
import pandas as pd
import numpy as np

sales = pd.read_csv("data/raw/daily_sales.csv", parse_dates=["date"])
inv = pd.read_csv("data/raw/inventory_snapshots.csv", parse_dates=["date"])
products = pd.read_csv("data/raw/products.csv")
suppliers = pd.read_csv("data/raw/suppliers.csv")

df = sales.merge(inv, on=["date", "sku", "warehouse_id"])
df = df.merge(products, on="sku").merge(suppliers, on="supplier_id")
df = df.sort_values(["sku", "warehouse_id", "date"]).reset_index(drop=True)

FORWARD_WINDOW = 14
BACKWARD_WINDOW = 30
SAMPLE_EVERY = 7

rows = []
for (sku, wh), g in df.groupby(["sku", "warehouse_id"]):
    g = g.reset_index(drop=True)
    n = len(g)

    avg_sales_7d = g["units_sold"].rolling(7, min_periods=3).mean()
    avg_sales_30d = g["units_sold"].rolling(30, min_periods=10).mean()
    std_sales_30d = g["units_sold"].rolling(30, min_periods=10).std()

    # forward-looking label: max stockout_flag over the NEXT 14 days
    # (strictly after the snapshot date)
    future_max = (
        g["stockout_flag"][::-1]
        .rolling(FORWARD_WINDOW, min_periods=1)
        .max()[::-1]
        .shift(-1)
    )

    for i in range(BACKWARD_WINDOW, n - FORWARD_WINDOW, SAMPLE_EVERY):
        a30 = avg_sales_30d.iloc[i]
        if pd.isna(a30) or a30 == 0:
            continue
        label = future_max.iloc[i]
        if pd.isna(label):
            continue
        rows.append({
            "date": g["date"].iloc[i],
            "sku": sku,
            "warehouse_id": wh,
            "category": g["category"].iloc[i],
            "on_hand_qty": g["on_hand_qty"].iloc[i],
            "on_order_qty": g["on_order_qty"].iloc[i],
            "avg_sales_7d": round(avg_sales_7d.iloc[i], 2),
            "avg_sales_30d": round(a30, 2),
            "demand_volatility_30d": round(std_sales_30d.iloc[i], 2) if not pd.isna(std_sales_30d.iloc[i]) else 0.0,
            "days_of_supply": round(g["on_hand_qty"].iloc[i] / a30, 2),
            "base_lead_time_days": g["base_lead_time_days"].iloc[i],
            "reliability_score": g["reliability_score"].iloc[i],
            "unit_cost": g["unit_cost"].iloc[i],
            "stockout_within_14d": int(label),
        })

features_df = pd.DataFrame(rows)
features_df.to_csv("data/processed/model_features.csv", index=False)

print("rows:", len(features_df))
print("positive rate:", round(features_df.stockout_within_14d.mean(), 3))
print(features_df.groupby("category").stockout_within_14d.mean().round(3))

# ---- latest snapshot per (sku, warehouse) for live scoring (no label needed) ----
latest_rows = []
for (sku, wh), g in df.groupby(["sku", "warehouse_id"]):
    g = g.reset_index(drop=True)
    i = len(g) - 1
    avg_sales_7d = g["units_sold"].rolling(7, min_periods=3).mean().iloc[i]
    avg_sales_30d = g["units_sold"].rolling(30, min_periods=10).mean().iloc[i]
    std_sales_30d = g["units_sold"].rolling(30, min_periods=10).std().iloc[i]
    if pd.isna(avg_sales_30d) or avg_sales_30d == 0:
        continue
    latest_rows.append({
        "date": g["date"].iloc[i],
        "sku": sku,
        "warehouse_id": wh,
        "product_name": g["product_name"].iloc[i],
        "category": g["category"].iloc[i],
        "on_hand_qty": g["on_hand_qty"].iloc[i],
        "on_order_qty": g["on_order_qty"].iloc[i],
        "avg_sales_7d": round(avg_sales_7d, 2),
        "avg_sales_30d": round(avg_sales_30d, 2),
        "demand_volatility_30d": round(std_sales_30d, 2) if not pd.isna(std_sales_30d) else 0.0,
        "days_of_supply": round(g["on_hand_qty"].iloc[i] / avg_sales_30d, 2),
        "base_lead_time_days": g["base_lead_time_days"].iloc[i],
        "reliability_score": g["reliability_score"].iloc[i],
        "unit_cost": g["unit_cost"].iloc[i],
        "supplier_id": g["supplier_id"].iloc[i],
    })
latest_df = pd.DataFrame(latest_rows)
latest_df.to_csv("data/processed/latest_snapshot_features.csv", index=False)
print("latest snapshot rows:", len(latest_df))
