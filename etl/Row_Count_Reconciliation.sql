
--  ROW COUNT RECONCILIATION
--  Telecom Customer Behavior & Fraud Analytics DWH

--  Purpose : Confirm that row counts are consistent between
--            the operational DB, staging layer, and DWH.
--            Detects silent data loss during ETL.
--  Run     : After every ETL load.
--  Engine  : DuckDB / PostgreSQL (ANSI-compatible)



--  SECTION 1 — OPERATIONAL DB TABLE COUNTS

SELECT
    'Operational DB'        AS layer,
    'customer'              AS table_name,
    COUNT(*)                AS row_count
FROM customer
UNION ALL
SELECT 'Operational DB', 'contract',   COUNT(*) FROM contract
UNION ALL
SELECT 'Operational DB', 'tariff',     COUNT(*) FROM tariff
UNION ALL
SELECT 'Operational DB', 'operator',   COUNT(*) FROM operator
UNION ALL
SELECT 'Operational DB', 'device',     COUNT(*) FROM device
UNION ALL
SELECT 'Operational DB', 'location',   COUNT(*) FROM location
UNION ALL
SELECT 'Operational DB', 'region',     COUNT(*) FROM region
UNION ALL
SELECT 'Operational DB', 'event_type', COUNT(*) FROM event_type
UNION ALL
SELECT 'Operational DB', 'channel',    COUNT(*) FROM channel
UNION ALL
SELECT 'Operational DB', 'invoice',    COUNT(*) FROM invoice
UNION ALL
SELECT 'Operational DB', 'payment',    COUNT(*) FROM payment
UNION ALL
SELECT 'Operational DB', 'cdr',        COUNT(*) FROM cdr
ORDER BY table_name;


--  SECTION 2 — STAGING LAYER COUNTS (per ETL status)

SELECT
    'Staging'               AS layer,
    etl_status,
    COUNT(*)                AS row_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct
FROM stg_cdr
GROUP BY etl_status
ORDER BY etl_status;

-- Staging total vs source CDR
SELECT
    'Reconciliation'        AS check_type,
    'STG total vs CDR total' AS description,
    (SELECT COUNT(*) FROM stg_cdr)    AS stg_rows,
    (SELECT COUNT(*) FROM cdr)        AS cdr_rows,
    (SELECT COUNT(*) FROM stg_cdr)
        - (SELECT COUNT(*) FROM cdr)  AS difference,
    CASE
        WHEN ABS((SELECT COUNT(*) FROM stg_cdr)
                 - (SELECT COUNT(*) FROM cdr)) = 0
        THEN '✓ MATCH'
        ELSE '⚠ MISMATCH — check extract window'
    END                     AS result;


--  SECTION 3 — DWH DIMENSION COUNTS

SELECT
    'DWH Dimension'         AS layer,
    'dim_customer (all)'    AS table_name,
    COUNT(*)                AS row_count
FROM dim_customer
UNION ALL
SELECT 'DWH Dimension', 'dim_customer (current)',
       COUNT(*) FROM dim_customer WHERE is_current = TRUE
UNION ALL
SELECT 'DWH Dimension', 'dim_customer (historical)',
       COUNT(*) FROM dim_customer WHERE is_current = FALSE
UNION ALL
SELECT 'DWH Dimension', 'dim_time',     COUNT(*) FROM dim_time
UNION ALL
SELECT 'DWH Dimension', 'dim_tariff',   COUNT(*) FROM dim_tariff
UNION ALL
SELECT 'DWH Dimension', 'dim_event',    COUNT(*) FROM dim_event
UNION ALL
SELECT 'DWH Dimension', 'dim_channel',  COUNT(*) FROM dim_channel
UNION ALL
SELECT 'DWH Dimension', 'dim_location', COUNT(*) FROM dim_location
UNION ALL
SELECT 'DWH Dimension', 'fact_usage_events', COUNT(*) FROM fact_usage_events
ORDER BY table_name;


--  SECTION 4 — SOURCE-TO-TARGET RECONCILIATION


-- Customer count: operational vs DWH (current rows only)
SELECT
    'Reconciliation'        AS check_type,
    'customer vs dim_customer (current)' AS description,
    (SELECT COUNT(*) FROM customer)                              AS source_rows,
    (SELECT COUNT(*) FROM dim_customer WHERE is_current = TRUE
     AND customer_id > 0)                                       AS dwh_rows,
    (SELECT COUNT(*) FROM customer) -
    (SELECT COUNT(*) FROM dim_customer WHERE is_current = TRUE
     AND customer_id > 0)                                       AS difference,
    CASE
        WHEN (SELECT COUNT(*) FROM customer) =
             (SELECT COUNT(*) FROM dim_customer
              WHERE is_current = TRUE AND customer_id > 0)
        THEN '✓ MATCH'
        ELSE '⚠ CHECK — SCD2 versions may exist or new customers pending'
    END                     AS result;

-- CDR valid rows vs fact rows loaded
SELECT
    'Reconciliation'        AS check_type,
    'STG VALID vs fact_usage_events' AS description,
    (SELECT COUNT(*) FROM stg_cdr WHERE etl_status = 'VALID') AS valid_staged,
    (SELECT COUNT(*) FROM fact_usage_events)                   AS fact_rows,
    CASE
        WHEN (SELECT COUNT(*) FROM fact_usage_events) > 0
        THEN '✓ Fact table populated'
        ELSE '✗ FAIL — no fact rows loaded'
    END                     AS result;


--  SECTION 5 — STAGING PASS RATE HISTORY

SELECT
    etl_load_date,
    COUNT(*)                                                     AS total_staged,
    SUM(CASE WHEN etl_status = 'VALID'    THEN 1 ELSE 0 END)    AS valid_rows,
    SUM(CASE WHEN etl_status = 'REJECTED' THEN 1 ELSE 0 END)    AS rejected_rows,
    ROUND(100.0 *
          SUM(CASE WHEN etl_status = 'VALID' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                                         AS pass_rate_pct
FROM stg_cdr
GROUP BY etl_load_date
ORDER BY etl_load_date DESC;
