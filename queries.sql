-- =====================================================================
-- PROJECT: Supply Chain & Stockout Risk Intelligence Platform
-- SQL business-logic layer. Standard ANSI SQL — runs on PostgreSQL,
-- MySQL 8+, and SQLite 3.25+.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. CURRENT DAYS-OF-SUPPLY PER SKU x WAREHOUSE (the core operational
--    metric: "how many days until this SKU runs out at current pace?")
-- ---------------------------------------------------------------------
WITH last_date AS (SELECT MAX(date) AS d FROM inventory_snapshots),
recent_sales AS (
    SELECT sku, warehouse_id, AVG(units_sold) AS avg_daily_sales_30d
    FROM daily_sales
    WHERE date > (SELECT date(d, '-30 days') FROM last_date)
    GROUP BY sku, warehouse_id
),
current_stock AS (
    SELECT i.sku, i.warehouse_id, i.on_hand_qty, i.on_order_qty
    FROM inventory_snapshots i
    JOIN last_date ld ON i.date = ld.d
)
SELECT
    c.sku, c.warehouse_id, c.on_hand_qty, c.on_order_qty,
    ROUND(r.avg_daily_sales_30d, 1)                                       AS avg_daily_sales_30d,
    ROUND(c.on_hand_qty / NULLIF(r.avg_daily_sales_30d, 0), 1)            AS days_of_supply,
    s.base_lead_time_days
FROM current_stock c
JOIN recent_sales r ON r.sku = c.sku AND r.warehouse_id = c.warehouse_id
JOIN products p ON p.sku = c.sku
JOIN suppliers s ON s.supplier_id = p.supplier_id
WHERE c.on_hand_qty / NULLIF(r.avg_daily_sales_30d, 0) < s.base_lead_time_days
ORDER BY days_of_supply ASC;
-- Finding: any row here is at risk — stock will likely run out before a
-- reorder placed today would even arrive.


-- ---------------------------------------------------------------------
-- 2. STOCKOUT INCIDENT COUNT (episodes, not days) — LAG window function
-- Business question: "How many distinct stockout EVENTS happened, not
-- just how many stockout-days (which double-counts a single 5-day
-- outage as 5 incidents)?"
-- ---------------------------------------------------------------------
WITH flagged AS (
    SELECT
        sku, warehouse_id, date, stockout_flag,
        LAG(stockout_flag) OVER (PARTITION BY sku, warehouse_id ORDER BY date) AS prev_flag
    FROM inventory_snapshots
)
SELECT
    sku, warehouse_id, COUNT(*) AS stockout_incidents
FROM flagged
WHERE stockout_flag = 1 AND (prev_flag = 0 OR prev_flag IS NULL)
GROUP BY sku, warehouse_id
ORDER BY stockout_incidents DESC
LIMIT 20;


-- ---------------------------------------------------------------------
-- 3. SUPPLIER LEAD-TIME ANOMALY DETECTION (the disruption-finder)
-- Business question: "Which suppliers had a sudden, sustained lead-time
-- blowout that operations should know about?"
-- ---------------------------------------------------------------------
WITH monthly AS (
    SELECT
        po.supplier_id,
        strftime('%Y-%m', po.order_date)                                          AS order_month,
        AVG(julianday(po.actual_delivery_date) - julianday(po.order_date))        AS avg_lead_time,
        s.base_lead_time_days
    FROM purchase_orders po
    JOIN suppliers s ON s.supplier_id = po.supplier_id
    GROUP BY po.supplier_id, order_month
)
SELECT
    supplier_id, order_month,
    ROUND(avg_lead_time, 1)                          AS avg_lead_time_days,
    base_lead_time_days,
    ROUND(avg_lead_time / base_lead_time_days, 2)    AS lead_time_ratio
FROM monthly
WHERE avg_lead_time > base_lead_time_days * 1.8       -- flag: lead time 80%+ above baseline
ORDER BY supplier_id, order_month;
-- Finding: exactly 3 suppliers flagged, exactly during a Jul-Sep window —
-- this is the kind of check that should run automatically every month,
-- not get discovered in a quarterly review.


-- ---------------------------------------------------------------------
-- 4. SUPPLIER PERFORMANCE SCORECARD
-- ---------------------------------------------------------------------
SELECT
    s.supplier_id, s.supplier_name, s.base_lead_time_days,
    ROUND(AVG(julianday(po.actual_delivery_date) - julianday(po.order_date)), 1)   AS avg_actual_lead_time,
    ROUND(100.0 * SUM(CASE WHEN po.actual_delivery_date <= po.expected_delivery_date THEN 1 ELSE 0 END) / COUNT(*), 1) AS on_time_rate_pct,
    COUNT(*)                                                                        AS total_pos
FROM purchase_orders po
JOIN suppliers s ON s.supplier_id = po.supplier_id
GROUP BY s.supplier_id
ORDER BY on_time_rate_pct ASC;


-- ---------------------------------------------------------------------
-- 5. LOST SALES $ VALUE — turning a stockout into a dollar figure
-- ---------------------------------------------------------------------
SELECT
    p.category,
    SUM(ds.units_demanded - ds.units_sold)                              AS lost_units,
    ROUND(SUM((ds.units_demanded - ds.units_sold) * p.unit_cost), 2)    AS lost_revenue_usd
FROM daily_sales ds
JOIN products p ON p.sku = ds.sku
GROUP BY p.category
ORDER BY lost_revenue_usd DESC;


-- ---------------------------------------------------------------------
-- 6. ABC ANALYSIS — classify SKUs by revenue contribution (NTILE)
-- Business question: "Which SKUs deserve tighter inventory control
-- (A-tier) vs. which can tolerate looser stock policy (C-tier)?"
-- ---------------------------------------------------------------------
WITH sku_revenue AS (
    SELECT ds.sku, SUM(ds.units_sold * p.unit_cost) AS revenue
    FROM daily_sales ds JOIN products p ON p.sku = ds.sku
    GROUP BY ds.sku
),
ranked AS (
    SELECT *, NTILE(10) OVER (ORDER BY revenue DESC) AS decile
    FROM sku_revenue
)
SELECT
    CASE WHEN decile <= 2 THEN 'A' WHEN decile <= 5 THEN 'B' ELSE 'C' END AS abc_tier,
    COUNT(*)                                                AS sku_count,
    ROUND(SUM(revenue), 0)                                  AS total_revenue,
    ROUND(100.0 * SUM(revenue) / (SELECT SUM(revenue) FROM sku_revenue), 1) AS pct_of_total_revenue
FROM ranked
GROUP BY abc_tier
ORDER BY abc_tier;


-- ---------------------------------------------------------------------
-- 7. MANUAL PIVOT — monthly demand by category (CASE WHEN pivot)
-- ---------------------------------------------------------------------
SELECT
    p.category,
    SUM(CASE WHEN strftime('%m', ds.date) = '01' THEN ds.units_demanded ELSE 0 END) AS jan,
    SUM(CASE WHEN strftime('%m', ds.date) = '06' THEN ds.units_demanded ELSE 0 END) AS jun,
    SUM(CASE WHEN strftime('%m', ds.date) = '11' THEN ds.units_demanded ELSE 0 END) AS nov,
    SUM(CASE WHEN strftime('%m', ds.date) = '12' THEN ds.units_demanded ELSE 0 END) AS dec
FROM daily_sales ds
JOIN products p ON p.sku = ds.sku
GROUP BY p.category
ORDER BY dec DESC;


-- ---------------------------------------------------------------------
-- 8. REORDER POLICY EFFECTIVENESS — did stockouts happen even though a
--    reorder had already been triggered? (signals the reorder POINT or
--    SAFETY STOCK is mis-calibrated, not that ops "forgot" to reorder)
-- ---------------------------------------------------------------------
WITH stockout_starts AS (
    SELECT sku, warehouse_id, date,
        LAG(stockout_flag) OVER (PARTITION BY sku, warehouse_id ORDER BY date) AS prev_flag
    FROM inventory_snapshots
    WHERE stockout_flag = 1
),
incidents AS (
    SELECT sku, warehouse_id, date AS stockout_date
    FROM stockout_starts
    WHERE prev_flag = 0 OR prev_flag IS NULL
)
SELECT
    i.sku, i.warehouse_id, i.stockout_date,
    (SELECT MAX(po.order_date) FROM purchase_orders po
     WHERE po.sku = i.sku AND po.warehouse_id = i.warehouse_id AND po.order_date < i.stockout_date) AS last_po_before_stockout
FROM incidents i
ORDER BY i.stockout_date
LIMIT 20;
