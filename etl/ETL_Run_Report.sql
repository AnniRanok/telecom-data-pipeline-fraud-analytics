
--  ETL RUN REPORT
--  Telecom Customer Behavior & Fraud Analytics DWH

--  Purpose : Generate a comprehensive summary report for each
--            ETL run covering all stages and quality results.
--  Run     : After every complete ETL cycle (Extract → Load).
--  Engine  : DuckDB / PostgreSQL (ANSI-compatible)

--  REPORT 1 — ETL RUN SUMMARY 

SELECT
    '=== ETL RUN SUMMARY ==='       AS section,
    NULL AS metric, NULL AS value
UNION ALL
SELECT NULL, 'Run Date',
    CAST(MAX(etl_load_date) AS VARCHAR)
FROM stg_cdr
UNION ALL
SELECT NULL, 'Total Staged',
    CAST(COUNT(*) AS VARCHAR)
FROM stg_cdr
WHERE etl_load_date = (SELECT MAX(etl_load_date) FROM stg_cdr)
UNION ALL
SELECT NULL, 'Valid Rows',
    CAST(SUM(CASE WHEN etl_status='VALID' THEN 1 ELSE 0 END) AS VARCHAR)
FROM stg_cdr
WHERE etl_load_date = (SELECT MAX(etl_load_date) FROM stg_cdr)
UNION ALL
SELECT NULL, 'Rejected Rows',
    CAST(SUM(CASE WHEN etl_status='REJECTED' THEN 1 ELSE 0 END) AS VARCHAR)
FROM stg_cdr
WHERE etl_load_date = (SELECT MAX(etl_load_date) FROM stg_cdr)
UNION ALL
SELECT NULL, 'Pass Rate %',
    CAST(ROUND(100.0 *
        SUM(CASE WHEN etl_status='VALID' THEN 1 ELSE 0 END) /
        NULLIF(COUNT(*), 0), 2) AS VARCHAR)
FROM stg_cdr
WHERE etl_load_date = (SELECT MAX(etl_load_date) FROM stg_cdr);


--  REPORT 2 — STAGE STATUS DISTRIBUTION

SELECT
    etl_load_date                                           AS run_date,
    etl_status,
    COUNT(*)                                                AS row_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER
          (PARTITION BY etl_load_date), 2)                  AS pct_of_batch
FROM stg_cdr
GROUP BY etl_load_date, etl_status
ORDER BY etl_load_date DESC, etl_status;


--  REPORT 3 — DWH TABLE SNAPSHOT (after latest load)

SELECT layer, table_name, row_count, status FROM (
    SELECT 'Business DB'  AS layer, 'customer'              AS table_name, COUNT(*) AS row_count, '—' AS status FROM customer
    UNION ALL SELECT 'Business DB',  'contract',            COUNT(*), '—' FROM contract
    UNION ALL SELECT 'Business DB',  'cdr',                 COUNT(*), '—' FROM cdr
    UNION ALL SELECT 'Business DB',  'invoice',             COUNT(*), '—' FROM invoice
    UNION ALL SELECT 'Business DB',  'payment',             COUNT(*), '—' FROM payment
    UNION ALL SELECT 'Staging',      'stg_cdr (VALID)',     COUNT(*), '✓' FROM stg_cdr WHERE etl_status='VALID'
    UNION ALL SELECT 'Staging',      'stg_cdr (REJECTED)',  COUNT(*),
        CASE WHEN COUNT(*)=0 THEN '✓' ELSE '⚠' END FROM stg_cdr WHERE etl_status='REJECTED'
    UNION ALL SELECT 'DWH',          'dim_customer (all)',  COUNT(*), '—' FROM dim_customer
    UNION ALL SELECT 'DWH',          'dim_customer (curr)', COUNT(*), '—' FROM dim_customer WHERE is_current=TRUE
    UNION ALL SELECT 'DWH',          'dim_time',            COUNT(*), '—' FROM dim_time
    UNION ALL SELECT 'DWH',          'dim_tariff',          COUNT(*), '—' FROM dim_tariff
    UNION ALL SELECT 'DWH',          'dim_event',           COUNT(*), '—' FROM dim_event
    UNION ALL SELECT 'DWH',          'dim_channel',         COUNT(*), '—' FROM dim_channel
    UNION ALL SELECT 'DWH',          'dim_location',        COUNT(*), '—' FROM dim_location
    UNION ALL SELECT 'DWH',          'fact_usage_events',   COUNT(*), '—' FROM fact_usage_events
) sub
ORDER BY
    CASE layer
        WHEN 'Business DB' THEN 1
        WHEN 'Staging'     THEN 2
        WHEN 'DWH'         THEN 3
    END,
    table_name;


--  REPORT 4 — SCD2 ACTIVITY REPORT

SELECT
    'SCD2 DIM_CUSTOMER Activity'    AS report,
    COUNT(*)                        AS total_rows,
    SUM(CASE WHEN is_current=TRUE  THEN 1 ELSE 0 END) AS current_rows,
    SUM(CASE WHEN is_current=FALSE THEN 1 ELSE 0 END) AS historical_rows,
    COUNT(DISTINCT customer_id) - 1 AS unique_customers, -- -1 for N/A placeholder
    SUM(CASE WHEN is_current=FALSE THEN 1 ELSE 0 END)
        AS total_scd2_versions_created
FROM dim_customer;

-- Customers with SCD2 history 
SELECT
    customer_id,
    COUNT(*)                        AS version_count,
    MIN(effective_from)             AS first_seen,
    MAX(CASE WHEN is_current=TRUE
             THEN effective_from END) AS last_updated
FROM dim_customer
WHERE customer_id > 0
GROUP BY customer_id
HAVING COUNT(*) > 1
ORDER BY version_count DESC
LIMIT 10;


--  REPORT 5 — FRAUD DETECTION SUMMARY

SELECT
    'Fraud Summary'                 AS report,
    COUNT(*)                        AS total_events,
    SUM(CASE WHEN fraud_score > 0.60 THEN 1 ELSE 0 END) AS high_risk_events,
    SUM(CASE WHEN fraud_score > 0.80 THEN 1 ELSE 0 END) AS critical_risk_events,
    ROUND(AVG(fraud_score), 4)      AS avg_fraud_score,
    MAX(fraud_score)                AS max_fraud_score,
    ROUND(100.0 *
          SUM(CASE WHEN fraud_score > 0.60 THEN 1 ELSE 0 END) /
          NULLIF(COUNT(*), 0), 3)   AS high_risk_rate_pct
FROM fact_usage_events;


--  REPORT 6 — REFERENTIAL INTEGRITY SUMMARY

SELECT check_name, orphan_rows,
       CASE WHEN orphan_rows = 0 THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM (
    SELECT 'FACT → DIM_CUSTOMER'  AS check_name,
           COUNT(*) AS orphan_rows
    FROM   fact_usage_events f
    WHERE  NOT EXISTS (SELECT 1 FROM dim_customer c WHERE c.customer_key = f.customer_key)
    UNION ALL
    SELECT 'FACT → DIM_TIME',      COUNT(*) FROM fact_usage_events f WHERE NOT EXISTS (SELECT 1 FROM dim_time     t WHERE t.time_key    = f.time_key)
    UNION ALL
    SELECT 'FACT → DIM_TARIFF',    COUNT(*) FROM fact_usage_events f WHERE NOT EXISTS (SELECT 1 FROM dim_tariff   t WHERE t.tariff_key  = f.tariff_key)
    UNION ALL
    SELECT 'FACT → DIM_EVENT',     COUNT(*) FROM fact_usage_events f WHERE NOT EXISTS (SELECT 1 FROM dim_event    e WHERE e.event_key   = f.event_key)
    UNION ALL
    SELECT 'FACT → DIM_CHANNEL',   COUNT(*) FROM fact_usage_events f WHERE NOT EXISTS (SELECT 1 FROM dim_channel  c WHERE c.channel_key = f.channel_key)
    UNION ALL
    SELECT 'FACT → DIM_LOCATION',  COUNT(*) FROM fact_usage_events f WHERE NOT EXISTS (SELECT 1 FROM dim_location l WHERE l.location_key= f.location_key)
    UNION ALL
    SELECT 'PAYMENT → INVOICE',    COUNT(*) FROM payment  p WHERE NOT EXISTS (SELECT 1 FROM invoice  i WHERE i.invoice_id  = p.invoice_id)
    UNION ALL
    SELECT 'DEVICE → CUSTOMER',    COUNT(*) FROM device   d WHERE NOT EXISTS (SELECT 1 FROM customer c WHERE c.customer_id = d.customer_id)
) sub
ORDER BY orphan_rows DESC;


--  REPORT 7 — REVENUE & USAGE KPI SNAPSHOT

SELECT
    'Revenue KPIs'                  AS report,
    ROUND(SUM(revenue_amount), 2)   AS total_revenue_eur,
    ROUND(AVG(revenue_amount), 4)   AS avg_per_event_eur,
    SUM(call_count)                 AS total_calls,
    SUM(sms_count)                  AS total_sms,
    ROUND(SUM(total_data_volume_mb) / 1024, 1) AS total_data_gb,
    SUM(event_count)                AS total_events,
    COUNT(DISTINCT customer_key)    AS active_customers
FROM fact_usage_events
WHERE customer_key > 0;  -- exclude N/A placeholder
