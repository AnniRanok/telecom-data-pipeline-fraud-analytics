
--  DATA QUALITY CHECK
--  Telecom Customer Behavior & Fraud Analytics DWH

--  Purpose : Validate data completeness, formats, and ranges
--            in both the operational DB and the staging layer.
--  Run     : After STAGE step, before LOAD step.
--  Expected: 0 rows returned per check (or review threshold).
--  Engine  : DuckDB / PostgreSQL (ANSI-compatible)


--  SECTION 1 — STAGING LAYER (STG_CDR)


-- DQ-01: NULL contract_id
SELECT
    'DQ-01'                         AS rule_id,
    'STG: NULL contract_id'         AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE contract_id IS NULL;

-- DQ-02: NULL event_key
SELECT
    'DQ-02'                         AS rule_id,
    'STG: NULL event_key'           AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE event_key IS NULL;

-- DQ-03: NULL event_datetime
SELECT
    'DQ-03'                         AS rule_id,
    'STG: NULL event_datetime'      AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE event_datetime IS NULL;

-- DQ-04: Negative duration_sec
SELECT
    'DQ-04'                         AS rule_id,
    'STG: duration_sec < 0'         AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE duration_sec < 0;

-- DQ-05: Negative data_volume_mb
SELECT
    'DQ-05'                         AS rule_id,
    'STG: data_volume_mb < 0'       AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE data_volume_mb < 0;

-- DQ-06: fraud_score out of range [0, 1]
SELECT
    'DQ-06'                         AS rule_id,
    'STG: fraud_score NOT IN [0,1]' AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE fraud_score < 0 OR fraud_score > 1;

-- DQ-07: Negative cost
SELECT
    'DQ-07'                         AS rule_id,
    'STG: cost < 0'                 AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE cost < 0;

-- DQ-08: Duplicate cdr_id in staging batch
SELECT
    'DQ-08'                         AS rule_id,
    'STG: Duplicate cdr_id'         AS check_name,
    COUNT(*) - COUNT(DISTINCT cdr_id) AS failed_rows,
    CASE WHEN COUNT(*) - COUNT(DISTINCT cdr_id) = 0
         THEN '✓ PASS' ELSE '✗ FAIL — deduplicate before load' END AS result
FROM stg_cdr;

-- DQ-09: Future event_datetime (sanity check)
SELECT
    'DQ-09'                         AS rule_id,
    'STG: event_datetime in future' AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '⚠ WARN — future timestamps detected' END AS result
FROM stg_cdr
WHERE CAST(event_datetime AS DATE) > CURRENT_DATE;

-- DQ-10: Invalid call_type values
SELECT
    'DQ-10'                         AS rule_id,
    'STG: Invalid call_type'        AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM stg_cdr
WHERE call_type NOT IN ('Outgoing', 'Incoming', 'N/A')
  AND call_type IS NOT NULL;


--  SECTION 2 — OPERATIONAL DB (BUSINESS DB)


-- DQ-11: Customer without first_name or last_name
SELECT
    'DQ-11'                         AS rule_id,
    'BIZ: Customer NULL name'       AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM customer
WHERE first_name IS NULL OR last_name IS NULL;

-- DQ-12: Customer segment not in allowed values
SELECT
    'DQ-12'                         AS rule_id,
    'BIZ: Invalid customer segment' AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM customer
WHERE segment NOT IN ('Budget','Standard','Premium','Business','Senior');

-- DQ-13: Contract end_date before start_date
SELECT
    'DQ-13'                         AS rule_id,
    'BIZ: Contract end < start'     AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM contract
WHERE end_date IS NOT NULL
  AND end_date <= start_date;

-- DQ-14: Tariff with negative monthly_fee
SELECT
    'DQ-14'                         AS rule_id,
    'BIZ: Tariff fee < 0'           AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM tariff
WHERE monthly_fee < 0;

-- DQ-15: Invoice total_amount negative or zero
SELECT
    'DQ-15'                         AS rule_id,
    'BIZ: Invoice amount <= 0'      AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM invoice
WHERE total_amount <= 0;

-- DQ-16: Location latitude out of Austria bounds [46.37, 49.02]
SELECT
    'DQ-16'                         AS rule_id,
    'BIZ: Latitude out of Austria'  AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '⚠ WARN' END AS result
FROM location
WHERE latitude  < 46.37 OR latitude  > 49.02
   OR longitude < 9.53  OR longitude > 17.16;

-- DQ-17: Device without customer reference
SELECT
    'DQ-17'                         AS rule_id,
    'BIZ: Device NULL customer_id'  AS check_name,
    COUNT(*)                        AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM device
WHERE customer_id IS NULL;


--  SECTION 3 — DWH DIMENSION QUALITY


-- DQ-18: DIM_CUSTOMER — SCD2: customer with more than 1 current row
SELECT
    'DQ-18'                              AS rule_id,
    'DWH: SCD2 duplicate current rows'  AS check_name,
    COUNT(*)                             AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL — SCD2 integrity broken' END AS result
FROM (
    SELECT customer_id
    FROM   dim_customer
    WHERE  is_current = TRUE
    GROUP  BY customer_id
    HAVING COUNT(*) > 1
) sub;

-- DQ-19: DIM_CUSTOMER — SCD2: effective_from > effective_to
SELECT
    'DQ-19'                              AS rule_id,
    'DWH: SCD2 date range invalid'      AS check_name,
    COUNT(*)                             AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM dim_customer
WHERE effective_to IS NOT NULL
  AND effective_from > effective_to;

-- DQ-20: DIM_TIME — missing expected row count (4 per day × 365)
SELECT
    'DQ-20'                              AS rule_id,
    'DWH: DIM_TIME row count check'     AS check_name,
    COUNT(*)                             AS actual_rows,
    CASE WHEN COUNT(*) >= 1460          -- 365 * 4 buckets
         THEN '✓ PASS'
         ELSE '⚠ WARN — DIM_TIME may be incomplete' END AS result
FROM dim_time
WHERE time_key > 0;  -- exclude N/A placeholder

-- DQ-21: FACT — fraud_score out of range
SELECT
    'DQ-21'                              AS rule_id,
    'DWH: FACT fraud_score NOT [0,1]'   AS check_name,
    COUNT(*)                             AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM fact_usage_events
WHERE fraud_score < 0 OR fraud_score > 1;

-- DQ-22: FACT — negative measures
SELECT
    'DQ-22'                              AS rule_id,
    'DWH: FACT negative measures'        AS check_name,
    COUNT(*)                             AS failed_rows,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM fact_usage_events
WHERE call_count              < 0
   OR sms_count               < 0
   OR total_call_duration_sec < 0
   OR total_data_volume_mb    < 0
   OR revenue_amount          < 0
   OR event_count             < 0;


--  SUMMARY — all DQ rules in one result set

SELECT rule_id, check_name, failed_rows,
       CASE WHEN failed_rows = 0 THEN '✓ PASS' ELSE '✗ FAIL' END AS result
FROM (
    SELECT 'DQ-01' AS rule_id, 'NULL contract_id'            AS check_name, COUNT(*) AS failed_rows FROM stg_cdr WHERE contract_id IS NULL
    UNION ALL SELECT 'DQ-02', 'NULL event_key',              COUNT(*) FROM stg_cdr WHERE event_key IS NULL
    UNION ALL SELECT 'DQ-03', 'NULL event_datetime',         COUNT(*) FROM stg_cdr WHERE event_datetime IS NULL
    UNION ALL SELECT 'DQ-04', 'duration_sec < 0',            COUNT(*) FROM stg_cdr WHERE duration_sec < 0
    UNION ALL SELECT 'DQ-05', 'data_volume_mb < 0',          COUNT(*) FROM stg_cdr WHERE data_volume_mb < 0
    UNION ALL SELECT 'DQ-06', 'fraud_score NOT IN [0,1]',    COUNT(*) FROM stg_cdr WHERE fraud_score < 0 OR fraud_score > 1
    UNION ALL SELECT 'DQ-07', 'cost < 0',                    COUNT(*) FROM stg_cdr WHERE cost < 0
    UNION ALL SELECT 'DQ-08', 'Duplicate cdr_id',            COUNT(*) - COUNT(DISTINCT cdr_id) FROM stg_cdr
    UNION ALL SELECT 'DQ-11', 'Customer NULL name',          COUNT(*) FROM customer WHERE first_name IS NULL OR last_name IS NULL
    UNION ALL SELECT 'DQ-12', 'Invalid segment',             COUNT(*) FROM customer WHERE segment NOT IN ('Budget','Standard','Premium','Business','Senior')
    UNION ALL SELECT 'DQ-13', 'Contract end < start',        COUNT(*) FROM contract WHERE end_date IS NOT NULL AND end_date <= start_date
    UNION ALL SELECT 'DQ-18', 'SCD2 duplicate current rows', COUNT(*) FROM (SELECT customer_id FROM dim_customer WHERE is_current=TRUE GROUP BY customer_id HAVING COUNT(*)>1) s
    UNION ALL SELECT 'DQ-19', 'SCD2 date range invalid',     COUNT(*) FROM dim_customer WHERE effective_to IS NOT NULL AND effective_from > effective_to
    UNION ALL SELECT 'DQ-21', 'FACT fraud_score NOT [0,1]',  COUNT(*) FROM fact_usage_events WHERE fraud_score < 0 OR fraud_score > 1
    UNION ALL SELECT 'DQ-22', 'FACT negative measures',      COUNT(*) FROM fact_usage_events WHERE call_count<0 OR sms_count<0 OR revenue_amount<0
) sub
ORDER BY failed_rows DESC, rule_id;
