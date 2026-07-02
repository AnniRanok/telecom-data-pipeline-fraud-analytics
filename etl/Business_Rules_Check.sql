
--  BUSINESS RULES CHECK
--  Telecom Customer Behavior & Fraud Analytics DWH

--  Purpose : Validate domain-specific business constraints
--            that go beyond simple NULL/range checks.
--  Run     : After ETL load, before analytics queries.
--  Engine  : DuckDB / PostgreSQL (ANSI-compatible)


--  SECTION 1 — CONTRACT RULES


-- BR-01: Each customer has at most 1 ACTIVE contract at a time
--  (Constraint: 1 customer holds exactly 1 active contract)
SELECT
    'BR-01'                                  AS rule_id,
    'Customer with > 1 active contract'      AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM (
    SELECT customer_id
    FROM   contract
    WHERE  status = 'Active'
    GROUP  BY customer_id
    HAVING COUNT(*) > 1
) sub;

-- BR-02: Each contract references a valid tariff
SELECT
    'BR-02'                                  AS rule_id,
    'Contract without valid tariff'          AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM contract ct
LEFT JOIN tariff t ON t.tariff_id = ct.tariff_id
WHERE t.tariff_id IS NULL;

-- BR-03: Closed contracts must have an end_date
SELECT
    'BR-03'                                  AS rule_id,
    'Closed contract without end_date'       AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM contract
WHERE status = 'Closed'
  AND end_date IS NULL;


--  SECTION 2 — TARIFF RULES

-- BR-04: Each tariff belongs to exactly 1 operator
SELECT
    'BR-04'                                  AS rule_id,
    'Tariff without operator'                AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM tariff t
LEFT JOIN operator o ON o.operator_id = t.operator_id
WHERE o.operator_id IS NULL;

-- BR-05: Tariff type must be Prepaid or Postpaid only
SELECT
    'BR-05'                                  AS rule_id,
    'Invalid tariff_type'                    AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM tariff
WHERE tariff_type NOT IN ('Prepaid', 'Postpaid');


--  SECTION 3 — CDR / EVENT RULES


-- BR-06: Voice calls (event_key IN 1,7) must have duration > 0
--  Exception: Short calls (event_key=11) may have duration 1-4 sec
SELECT
    'BR-06'                                  AS rule_id,
    'Voice call with zero duration'          AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '⚠ WARN — check short call logic' END AS result
FROM cdr
WHERE event_key IN (1, 7)
  AND duration_sec = 0;

-- BR-07: Data sessions must have data_volume_mb > 0
SELECT
    'BR-07'                                  AS rule_id,
    'Data session with zero volume'          AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '⚠ WARN' END                  AS result
FROM cdr
WHERE event_key = 3      -- Data Session Start
  AND data_volume_mb = 0;

-- BR-08: No CDR events outside simulation period
SELECT
    'BR-08'                                  AS rule_id,
    'CDR outside simulation period'          AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '⚠ WARN — events outside 2024 window' END AS result
FROM cdr
WHERE CAST(event_datetime AS DATE) < DATE '2024-01-01'
   OR CAST(event_datetime AS DATE) > DATE '2024-12-31';

-- BR-09: Fraud score > 0.6 only for flagged events
SELECT
    'BR-09'                                  AS rule_id,
    'High fraud_score without fraud_flag'    AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '⚠ WARN — score/flag mismatch' END AS result
FROM cdr
WHERE fraud_score > 0.60
  AND fraud_flag = FALSE;


--  SECTION 4 — BILLING CHAIN RULES


-- BR-10: Every invoice references an active or closed contract
SELECT
    'BR-10'                                  AS rule_id,
    'Invoice for non-existent contract'      AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM invoice i
LEFT JOIN contract ct ON ct.contract_id = i.contract_id
WHERE ct.contract_id IS NULL;

-- BR-11: Payment references an existing invoice (FK_payment_invoice)
SELECT
    'BR-11'                                  AS rule_id,
    'Payment without valid invoice'          AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS' ELSE '✗ FAIL' END    AS result
FROM payment p
LEFT JOIN invoice i ON i.invoice_id = p.invoice_id
WHERE i.invoice_id IS NULL;

-- BR-12: Payment amount should match invoice total_amount (tolerance ±5%)
SELECT
    'BR-12'                                  AS rule_id,
    'Payment amount far from invoice amount' AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '⚠ WARN — verify billing logic' END AS result
FROM payment p
JOIN invoice i ON i.invoice_id = p.invoice_id
WHERE ABS(p.amount - i.total_amount) > i.total_amount * 0.05;


--  SECTION 5 — DWH BUSINESS RULES


-- BR-13: Fact grain uniqueness
--  Each (customer_key, time_key, tariff_key, event_key,
--         channel_key, location_key) should be unique
SELECT
    'BR-13'                                  AS rule_id,
    'Duplicate fact grain rows'              AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '✗ FAIL — grain not unique, check GROUP BY' END AS result
FROM (
    SELECT
        customer_key, time_key, tariff_key,
        event_key, channel_key, location_key,
        COUNT(*) AS n
    FROM fact_usage_events
    GROUP BY
        customer_key, time_key, tariff_key,
        event_key, channel_key, location_key
    HAVING COUNT(*) > 1
) sub;

-- BR-14: N/A placeholder exists in all dimensions
SELECT
    'BR-14'                                  AS rule_id,
    'N/A placeholder (key=-1) missing'       AS rule_name,
    CASE
        WHEN EXISTS (SELECT 1 FROM dim_customer WHERE customer_key = -1)
        THEN 0 ELSE 1
    END                                      AS violations,
    CASE
        WHEN EXISTS (SELECT 1 FROM dim_customer WHERE customer_key = -1)
        THEN '✓ PASS (dim_customer N/A exists)'
        ELSE '✗ FAIL — dim_customer N/A row missing'
    END                                      AS result;

-- BR-15: SCD2 — no gap between effective_to and next effective_from
--  For each customer, the versions should be contiguous
SELECT
    'BR-15'                                  AS rule_id,
    'SCD2 version gaps detected'             AS rule_name,
    COUNT(*)                                 AS violations,
    CASE WHEN COUNT(*) = 0
         THEN '✓ PASS'
         ELSE '⚠ WARN — check SCD2 close logic' END AS result
FROM (
    SELECT
        a.customer_id,
        a.effective_to,
        b.effective_from,
        b.effective_from - a.effective_to AS gap_days
    FROM dim_customer a
    JOIN dim_customer b
      ON  b.customer_id    = a.customer_id
      AND b.effective_from > a.effective_from
      AND a.is_current     = FALSE
    WHERE a.effective_to IS NOT NULL
      AND b.effective_from > a.effective_to + 1
) sub;


--  SUMMARY — all business rules

SELECT rule_id, rule_name, violations,
       CASE WHEN violations = 0 THEN '✓ PASS' ELSE '✗ FAIL / ⚠ WARN' END AS result
FROM (
    SELECT 'BR-01' AS rule_id, 'Customer > 1 active contract'         AS rule_name, COUNT(*) AS violations FROM (SELECT customer_id FROM contract WHERE status='Active' GROUP BY customer_id HAVING COUNT(*)>1) s
    UNION ALL SELECT 'BR-03', 'Closed contract without end_date',      COUNT(*) FROM contract WHERE status='Closed' AND end_date IS NULL
    UNION ALL SELECT 'BR-05', 'Invalid tariff_type',                   COUNT(*) FROM tariff WHERE tariff_type NOT IN ('Prepaid','Postpaid')
    UNION ALL SELECT 'BR-09', 'High score without fraud_flag',         COUNT(*) FROM cdr WHERE fraud_score>0.60 AND fraud_flag=FALSE
    UNION ALL SELECT 'BR-10', 'Invoice for missing contract',          COUNT(*) FROM invoice i LEFT JOIN contract ct ON ct.contract_id=i.contract_id WHERE ct.contract_id IS NULL
    UNION ALL SELECT 'BR-11', 'Payment without invoice',               COUNT(*) FROM payment p LEFT JOIN invoice i ON i.invoice_id=p.invoice_id WHERE i.invoice_id IS NULL
    UNION ALL SELECT 'BR-13', 'Duplicate fact grain',                  COUNT(*) FROM (SELECT customer_key,time_key,tariff_key,event_key,channel_key,location_key FROM fact_usage_events GROUP BY customer_key,time_key,tariff_key,event_key,channel_key,location_key HAVING COUNT(*)>1) s
    UNION ALL SELECT 'BR-14', 'DIM_CUSTOMER N/A placeholder missing',  CASE WHEN EXISTS(SELECT 1 FROM dim_customer WHERE customer_key=-1) THEN 0 ELSE 1 END
) sub
ORDER BY violations DESC, rule_id;
