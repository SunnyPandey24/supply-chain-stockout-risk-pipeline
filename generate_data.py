"""
Generates a synthetic multi-warehouse retail supply-chain dataset:
products, suppliers, warehouses, daily_sales, purchase_orders,
inventory_snapshots. Simulates real inventory dynamics day-by-day
(demand, reordering, lead times, and supplier disruptions) so that
stockouts in the output are a genuine emergent pattern, not a label
bolted on afterward.
"""
import random
import datetime as dt
import numpy as np
import pandas as pd
from faker import Faker

fake = Faker()
random.seed(11)
np.random.seed(11)

N_SKUS = 40
N_WAREHOUSES = 4
N_SUPPLIERS = 10
START = dt.date(2023, 1, 1)
END = dt.date(2023, 12, 31)
N_DAYS = (END - START).days + 1
DATES = [START + dt.timedelta(days=i) for i in range(N_DAYS)]

CATEGORIES = ["Electronics", "Apparel", "Garden", "Grocery", "Toys", "HomeGoods"]
REGIONS = ["North", "South", "East", "West"]

def season_weight(category, month):
    base = {
        "Electronics": {11: 1.8, 12: 2.0, 1: 0.8},
        "Apparel":     {3: 1.3, 4: 1.3, 11: 1.4, 12: 1.5},
        "Garden":      {4: 1.8, 5: 2.0, 6: 1.7, 7: 1.4, 1: 0.4, 12: 0.4},
        "Grocery":     {11: 1.3, 12: 1.5},
        "Toys":        {11: 1.9, 12: 2.2},
        "HomeGoods":   {1: 1.2, 11: 1.3, 12: 1.4},
    }
    return base.get(category, {}).get(month, 1.0)

# ---- suppliers ----
suppliers = []
for i in range(1, N_SUPPLIERS + 1):
    suppliers.append({
        "supplier_id": i,
        "supplier_name": fake.company(),
        "region": random.choice(REGIONS),
        "base_lead_time_days": random.randint(5, 21),
        "reliability_score": round(random.uniform(0.75, 0.99), 2),
    })
suppliers_df = pd.DataFrame(suppliers)

# pick 3 suppliers that will suffer a disruption (3x lead time) for a window
disrupted_suppliers = random.sample(range(1, N_SUPPLIERS + 1), 3)
disruption_start = dt.date(2023, 7, 15)
disruption_end = dt.date(2023, 9, 15)

# ---- warehouses ----
warehouses = [{"warehouse_id": i, "warehouse_name": f"DC-{r}", "region": r}
              for i, r in enumerate(REGIONS, start=1)]
warehouses_df = pd.DataFrame(warehouses)

# ---- products ----
products = []
for i in range(1, N_SKUS + 1):
    cat = random.choice(CATEGORIES)
    cost = round(random.uniform(*{
        "Electronics": (40, 350), "Apparel": (8, 60), "Garden": (10, 90),
        "Grocery": (2, 25), "Toys": (5, 70), "HomeGoods": (15, 150)
    }[cat]), 2)
    products.append({
        "sku": f"SKU{i:04d}",
        "product_name": fake.word().title() + " " + cat,
        "category": cat,
        "unit_cost": cost,
        "supplier_id": random.randint(1, N_SUPPLIERS),
    })
products_df = pd.DataFrame(products)
supplier_map = products_df.set_index("sku")["supplier_id"].to_dict()
category_map = products_df.set_index("sku")["category"].to_dict()
supplier_info = suppliers_df.set_index("supplier_id").to_dict("index")

# ---- simulate per (sku, warehouse) ----
daily_sales_rows = []
inventory_rows = []
po_rows = []
po_id_counter = 1

for sku in products_df.sku:
    cat = category_map[sku]
    sup_id = supplier_map[sku]
    sup = supplier_info[sup_id]
    base_lead_time = sup["base_lead_time_days"]
    reliability = sup["reliability_score"]

    for wh in warehouses_df.warehouse_id:
        avg_demand = np.random.uniform(3, 40)               # base units/day
        safety_factor = np.random.uniform(1.1, 1.6)         # imperfect, allows some stockouts
        order_qty = int(avg_demand * base_lead_time * np.random.uniform(1.5, 2.5))
        reorder_point = avg_demand * base_lead_time * safety_factor

        stock = int(order_qty * np.random.uniform(0.8, 1.3))
        open_pos = []  # list of dicts: {expected_delivery, qty}

        for d in DATES:
            month = d.month
            weekday_factor = 0.85 if d.weekday() >= 5 else 1.0
            demand = max(0, np.random.poisson(avg_demand * season_weight(cat, month) * weekday_factor))

            # receive any arriving POs
            arrived = [po for po in open_pos if po["expected_delivery"] == d]
            for po in arrived:
                stock += po["qty"]
            open_pos = [po for po in open_pos if po["expected_delivery"] != d]

            units_sold = min(demand, stock)
            stock -= units_sold
            stockout_flag = 1 if stock <= 0 else 0

            daily_sales_rows.append({
                "date": d, "sku": sku, "warehouse_id": wh,
                "units_demanded": demand, "units_sold": units_sold
            })
            inventory_rows.append({
                "date": d, "sku": sku, "warehouse_id": wh,
                "on_hand_qty": stock, "on_order_qty": sum(po["qty"] for po in open_pos),
                "stockout_flag": stockout_flag
            })

            # reorder logic
            if stock <= reorder_point and len(open_pos) == 0:
                lead_time = base_lead_time
                if sup_id in disrupted_suppliers and disruption_start <= d <= disruption_end:
                    lead_time = int(base_lead_time * 3)
                # reliability affects random delay on top of base lead time
                delay = 0 if random.random() < reliability else random.randint(2, 7)
                expected_delivery = d + dt.timedelta(days=lead_time + delay)
                open_pos.append({"expected_delivery": expected_delivery, "qty": order_qty})
                po_rows.append({
                    "po_id": po_id_counter, "sku": sku, "warehouse_id": wh,
                    "supplier_id": sup_id, "order_date": d,
                    "expected_delivery_date": d + dt.timedelta(days=lead_time),
                    "actual_delivery_date": expected_delivery,
                    "qty_ordered": order_qty
                })
                po_id_counter += 1

daily_sales_df = pd.DataFrame(daily_sales_rows)
inventory_df = pd.DataFrame(inventory_rows)
po_df = pd.DataFrame(po_rows)

products_df.to_csv("data/raw/products.csv", index=False)
suppliers_df.to_csv("data/raw/suppliers.csv", index=False)
warehouses_df.to_csv("data/raw/warehouses.csv", index=False)
daily_sales_df.to_csv("data/raw/daily_sales.csv", index=False)
inventory_df.to_csv("data/raw/inventory_snapshots.csv", index=False)
po_df.to_csv("data/raw/purchase_orders.csv", index=False)

print("daily_sales", len(daily_sales_df))
print("inventory_snapshots", len(inventory_df))
print("purchase_orders", len(po_df))
print("stockout days:", inventory_df.stockout_flag.sum(), "/", len(inventory_df),
      f"({100*inventory_df.stockout_flag.mean():.1f}%)")
print("disrupted_suppliers", disrupted_suppliers)
