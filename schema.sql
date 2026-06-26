DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS inventory_snapshots;
DROP TABLE IF EXISTS daily_sales;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS warehouses;

CREATE TABLE suppliers (
    supplier_id         INTEGER PRIMARY KEY,
    supplier_name        TEXT NOT NULL,
    region               TEXT NOT NULL,
    base_lead_time_days  INTEGER NOT NULL,
    reliability_score    NUMERIC(4,2) NOT NULL
);

CREATE TABLE warehouses (
    warehouse_id    INTEGER PRIMARY KEY,
    warehouse_name  TEXT NOT NULL,
    region          TEXT NOT NULL
);

CREATE TABLE products (
    sku            TEXT PRIMARY KEY,
    product_name   TEXT NOT NULL,
    category       TEXT NOT NULL,
    unit_cost      NUMERIC(10,2) NOT NULL,
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(supplier_id)
);

CREATE TABLE daily_sales (
    date            DATE NOT NULL,
    sku             TEXT NOT NULL REFERENCES products(sku),
    warehouse_id    INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    units_demanded  INTEGER NOT NULL,
    units_sold      INTEGER NOT NULL
);

CREATE TABLE inventory_snapshots (
    date            DATE NOT NULL,
    sku             TEXT NOT NULL REFERENCES products(sku),
    warehouse_id    INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    on_hand_qty     INTEGER NOT NULL,
    on_order_qty    INTEGER NOT NULL,
    stockout_flag   INTEGER NOT NULL CHECK (stockout_flag IN (0,1))
);

CREATE TABLE purchase_orders (
    po_id                   INTEGER PRIMARY KEY,
    sku                     TEXT NOT NULL REFERENCES products(sku),
    warehouse_id            INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    supplier_id             INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    order_date              DATE NOT NULL,
    expected_delivery_date  DATE NOT NULL,
    actual_delivery_date    DATE NOT NULL,
    qty_ordered             INTEGER NOT NULL
);

CREATE INDEX idx_sales_sku_wh_date ON daily_sales(sku, warehouse_id, date);
CREATE INDEX idx_inv_sku_wh_date ON inventory_snapshots(sku, warehouse_id, date);
CREATE INDEX idx_po_sku_wh ON purchase_orders(sku, warehouse_id);
CREATE INDEX idx_po_supplier ON purchase_orders(supplier_id);
