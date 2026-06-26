"""Loads the CSVs in data/raw/ into a local SQLite database
(sql/supply_chain.db) for testing queries.sql.
Run `sqlite3 sql/supply_chain.db < sql/schema.sql` first, or this
script will create the schema for you if the db doesn't exist."""
import sqlite3
import pandas as pd
import os

DB_PATH = "sql/supply_chain.db"
if not os.path.exists(DB_PATH):
    con = sqlite3.connect(DB_PATH)
    con.executescript(open("sql/schema.sql").read())
else:
    con = sqlite3.connect(DB_PATH)

tables = ["suppliers", "warehouses", "products", "daily_sales",
          "inventory_snapshots", "purchase_orders"]
for t in tables:
    df = pd.read_csv(f"data/raw/{t}.csv")
    df.to_sql(t, con, if_exists="append", index=False)
con.commit()
con.close()
print("Loaded:", ", ".join(tables))
