
--  ANALYTICAL QUERIES
--  Telecom Customer Behavior & Fraud Analytics Platform

-- Run against the warehouse database (db/dwh.duckdb).
-- ANSI-compatible — works unchanged against PostgreSQL.


-- Q1: Revenue by tariff plan
-- Identifies which plans drive the most revenue and how revenue
-- is distributed across the active customer base.
SELECT
    t.tariff_name,
    t.tariff_type,
    t.operator_name,
    COUNT(DISTINCT f.customer_key)          AS active_customers,
    ROUND(SUM(f.revenue_amount), 2)         AS total_revenue_eur,
    ROUND(AVG(f.revenue_amount), 4)         AS avg_revenue_per_event,
    ROUND(SUM(f.revenue_amount) /
          NULLIF(COUNT(DISTINCT f.customer_key), 0), 2) AS revenue_per_customer
FROM   fact_usage_events f
JOIN   dim_tariff t ON t.tariff_key = f.tariff_key
GROUP  BY t.tariff_name, t.tariff_type, t.operator_name
ORDER  BY total_revenue_eur DESC;


-- Q2: Call frequency by time of day and weekday
-- Surfaces peak usage windows for network capacity planning.
SELECT
    d.time_of_day,
    d.day_name,
    d.is_weekend,
    SUM(f.call_count)                    AS total_calls,
    SUM(f.total_call_duration_sec) / 60  AS total_minutes,
    COUNT(DISTINCT f.customer_key)       AS unique_callers
FROM   fact_usage_events f
JOIN   dim_time d ON d.time_key = f.time_key
GROUP  BY d.time_of_day, d.day_name, d.is_weekend
ORDER  BY total_calls DESC;


-- Q3: Data usage by customer segment over time
-- Tracks how usage volume evolves per segment, month over month.
SELECT
    d.month_name,
    d.quarter,
    c.segment,
    COUNT(DISTINCT f.customer_key)               AS customers,
    ROUND(SUM(f.total_data_volume_mb) / 1024, 2) AS total_data_gb,
    ROUND(AVG(f.total_data_volume_mb), 2)        AS avg_data_mb_per_event,
    SUM(f.sms_count)                              AS total_sms
FROM   fact_usage_events f
JOIN   dim_customer c ON c.customer_key = f.customer_key AND c.is_current = TRUE
JOIN   dim_time     d ON d.time_key     = f.time_key
GROUP  BY d.month_name, d.quarter, c.segment
ORDER  BY d.quarter, c.segment;


-- Q4: Fraud concentration by region
-- Highlights geographic hotspots for elevated fraud risk.
SELECT
    l.region,
    l.area_type,
    COUNT(*)                                               AS total_events,
    SUM(CASE WHEN f.fraud_score > 0.6 THEN 1 ELSE 0 END)   AS high_risk_events,
    ROUND(AVG(f.fraud_score), 3)                           AS avg_fraud_score,
    MAX(f.fraud_score)                                     AS max_fraud_score,
    ROUND(100.0 * SUM(CASE WHEN f.fraud_score > 0.6 THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 2)                        AS fraud_rate_pct
FROM   fact_usage_events f
JOIN   dim_location l ON l.location_key = f.location_key
GROUP  BY l.region, l.area_type
ORDER  BY avg_fraud_score DESC;



--  DATA QUALITY / ETL VERIFICATION QUERIES


-- Orphan foreign keys in the fact table
SELECT 'fact -> dim_time orphans' AS check_name, COUNT(*) AS n
FROM   fact_usage_events f
WHERE  NOT EXISTS (SELECT 1 FROM dim_time t WHERE t.time_key = f.time_key)
UNION ALL
SELECT 'fact -> dim_customer orphans', COUNT(*)
FROM   fact_usage_events f
WHERE  NOT EXISTS (SELECT 1 FROM dim_customer c WHERE c.customer_key = f.customer_key);

-- Staging pass/reject rate
SELECT
    etl_load_date,
    COUNT(*)                                                  AS total_staged,
    SUM(CASE WHEN etl_status = 'VALID'    THEN 1 ELSE 0 END)  AS valid_rows,
    SUM(CASE WHEN etl_status = 'REJECTED' THEN 1 ELSE 0 END)  AS rejected_rows,
    ROUND(100.0 * SUM(CASE WHEN etl_status = 'VALID' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                                      AS pass_pct
FROM   stg_cdr
GROUP  BY etl_load_date
ORDER  BY etl_load_date DESC;

-- SCD2 integrity: each customer must have exactly one current row
SELECT customer_id, COUNT(*) AS n_current
FROM   dim_customer
WHERE  is_current = TRUE
GROUP  BY customer_id
HAVING COUNT(*) > 1;
