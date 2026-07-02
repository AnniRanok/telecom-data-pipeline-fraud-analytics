
--  Storage Space Calculation
--  Telecom Customer Behavior & Fraud Analytics Platform

--  Methode: Zeilengröße (bytes) × Zeilenanzahl = Tabellengröße
--  Datentyp-Größen (SQL Server / DuckDB):
--    INT / INTEGER     = 4 Bytes
--    BIGINT            = 8 Bytes
--    DECIMAL(8,2)      = 9 Bytes
--    DECIMAL(10,6)     = 9 Bytes
--    DECIMAL(12,4)     = 9 Bytes
--    DECIMAL(18,2)     = 9 Bytes
--    DECIMAL(5,2)      = 5 Bytes
--    VARCHAR(n)        = ~n/2 Bytes (Durchschnitt, variabel)
--    CHAR(1)           = 1 Byte
--    DATE              = 3 Bytes
--    TIMESTAMP         = 8 Bytes
--    BOOLEAN           = 1 Byte
--  Overhead pro Zeile: ~20 Bytes (Row Header, NULL-Bitmap)

--  SECTION 1 — OPERATIONAL DATABASE (Business DB)


/*
TABLE: customer
Columns:
  customer_id     INT          4
  first_name      VARCHAR(80)  40 (avg)
  last_name       VARCHAR(80)  40 (avg)
  gender          CHAR(1)       1
  birth_date      DATE          3
  age             INT           4
  profession      VARCHAR(80)  30 (avg)
  city            VARCHAR(80)  20 (avg)
  country         VARCHAR(60)  10 (avg = 'Austria')
  region_id       INT           4
  segment         VARCHAR(20)  10 (avg)
  customer_status VARCHAR(20)   8 (avg = 'Active')
  created_at      DATE          3
  Row overhead:                20
  ─────────────────────────────
  Zeilengröße:                197 Bytes ≈ 200 Bytes

Zielwert: 50.000 Kunden
Tabellengröße: 200 × 50.000 = 10.000.000 Bytes = 9,5 MB
*/

-- TABLE: contract
/*
  contract_id  INT      4
  customer_id  INT      4
  tariff_id    INT      4
  start_date   DATE     3
  end_date     DATE     3
  status       VARCHAR(20) 8 (avg)
  Overhead:           20
  ─────────────────
  Zeilengröße:        46 Bytes ≈ 50 Bytes

Zielwert: 60.000 Verträge
Tabellengröße: 50 × 60.000 = 3.000.000 Bytes = 2,9 MB
*/

-- TABLE: cdr (Kerntransaktionstabelle)
/*
  cdr_id          BIGINT        8
  contract_id     INT           4
  receiver_id     INT           4
  channel_id      INT           4
  event_key       INT           4
  event_datetime  TIMESTAMP     8
  duration_sec    INT           4
  data_volume_mb  DECIMAL(12,4) 9
  location_id     INT           4
  cost            DECIMAL(10,4) 9
  call_type       VARCHAR(20)   8 (avg)
  fraud_flag      BOOLEAN       1
  fraud_score     DECIMAL(5,2)  5
  fraud_scenario  VARCHAR(60)  10 (avg, meist NULL)
  created_at      TIMESTAMP     8
  Overhead:                    20
  ─────────────────────────────
  Zeilengröße:                110 Bytes ≈ 115 Bytes

Zielwert: ~3.000.000 Datensätze (50k Kunden × 365 Tage × ~16% Aktivitätsrate)
Tabellengröße: 115 × 3.000.000 = 345.000.000 Bytes = 329 MB
*/

-- TABLE: invoice
/*
  invoice_id      BIGINT        8
  contract_id     INT           4
  billing_period  VARCHAR(7)    7
  total_amount    DECIMAL(10,2) 9
  status          VARCHAR(20)   8 (avg)
  Overhead:                    20
  ─────────────────────────────
  Zeilengröße:                 56 Bytes

Zielwert: 60.000 Verträge × 12 Monate = 720.000 Zeilen
Tabellengröße: 56 × 720.000 = 40.320.000 Bytes = 38,5 MB
*/

-- TABLE: payment
/*
  payment_id  BIGINT        8
  invoice_id  BIGINT        8
  amount      DECIMAL(10,2) 9
  pay_date    DATE          3
  method      VARCHAR(40)  20 (avg)
  Overhead:                20
  ─────────────────────────
  Zeilengröße:             68 Bytes

Zielwert: ~650.000 Zahlungen (90% der Rechnungen bezahlt)
Tabellengröße: 68 × 650.000 = 44.200.000 Bytes = 42,2 MB
*/

-- Zusammenfassung Operational DB
SELECT
    table_name,
    col_count,
    row_size_bytes,
    target_rows,
    (row_size_bytes * target_rows)                    AS total_bytes,
    ROUND((row_size_bytes * target_rows) / 1048576.0, 2) AS size_mb
FROM (VALUES
    ('customer',    13,  200,      50000),
    ('contract',     6,   50,      60000),
    ('tariff',      10,   80,         10),
    ('operator',     3,   50,          3),
    ('device',       7,  120,      50000),
    ('location',     8,  100,       2000),
    ('region',       3,   50,          9),
    ('event_type',   5,   80,         11),
    ('channel',      3,   50,          6),
    ('invoice',      5,   56,     720000),
    ('payment',      5,   68,     650000),
    ('cdr',         15,  115,    3000000)
) AS t(table_name, col_count, row_size_bytes, target_rows)
ORDER BY total_bytes DESC;

-- Gesamtgröße Operational DB
SELECT
    'TOTAL — Operational DB'            AS summary,
    SUM(row_size_bytes * target_rows)   AS total_bytes,
    ROUND(SUM(row_size_bytes * target_rows) / 1048576.0, 1) AS total_mb,
    ROUND(SUM(row_size_bytes * target_rows) / 1073741824.0, 3) AS total_gb
FROM (VALUES
    (200,  50000),
    ( 50,  60000),
    ( 80,     10),
    ( 50,      3),
    (120,  50000),
    (100,   2000),
    ( 50,      9),
    ( 80,     11),
    ( 50,      6),
    ( 56, 720000),
    ( 68, 650000),
    (115,3000000)
) AS t(row_size_bytes, target_rows);


--  SECTION 2 — DATA WAREHOUSE (Star Schema)


/*
TABLE: fact_usage_events (Faktentabelle)
  usage_event_key       BIGINT        8
  customer_key           BIGINT        8
  time_key                INT          4
  tariff_key              INT          4
  event_key                INT          4
  channel_key              INT          4
  location_key             INT          4
  call_count               INT          4
  sms_count                INT          4
  total_call_duration_sec  INT          4
  total_data_volume_mb     DECIMAL(18,2) 9
  revenue_amount           DECIMAL(18,2) 9
  roaming_revenue          DECIMAL(18,2) 9
  international_revenue    DECIMAL(18,2) 9
  discount_amount          DECIMAL(18,2) 9
  fraud_score               DECIMAL(5,2)  5
  event_count               INT          4
  Overhead:                             20
  ─────────────────────────────────────────
  Zeilengröße:                         132 Bytes ≈ 135 Bytes

Zielwert: ~3.000.000 Zeilen (aggregiertes Grain)
Tabellengröße: 135 × 3.000.000 = 405.000.000 Bytes = 386 MB
*/

-- DWH Zusammenfassung
SELECT
    table_name,
    scd_type,
    row_size_bytes,
    target_rows,
    (row_size_bytes * target_rows)                       AS total_bytes,
    ROUND((row_size_bytes * target_rows) / 1048576.0, 2) AS size_mb
FROM (VALUES
    ('fact_usage_events', '—',       135, 3000000),
    ('dim_customer',      'SCD2',    220,   55000),  -- 50k + 10% SCD2 versions
    ('dim_time',          'SCD1',     90,    1464),  -- 365 days × 4 buckets
    ('dim_tariff',        'SCD1',    120,      10),
    ('dim_event',         'SCD1',     80,      11),
    ('dim_channel',       'SCD1',     70,       6),
    ('dim_location',      'SCD1',    115,    2000),
    ('stg_cdr',           'Staging', 150, 3000000)   -- same grain as fact
) AS t(table_name, scd_type, row_size_bytes, target_rows)
ORDER BY total_bytes DESC;

-- Gesamtgröße DWH
SELECT
    'TOTAL — Data Warehouse'            AS summary,
    SUM(row_size_bytes * target_rows)   AS total_bytes,
    ROUND(SUM(row_size_bytes * target_rows) / 1048576.0, 1) AS total_mb,
    ROUND(SUM(row_size_bytes * target_rows) / 1073741824.0, 3) AS total_gb
FROM (VALUES
    (135,3000000),
    (220,  55000),
    ( 90,   1464),
    (120,     10),
    ( 80,     11),
    ( 70,      6),
    (115,   2000),
    (150,3000000)
) AS t(row_size_bytes, target_rows);



--  SECTION 3 — GESAMTÜBERSICHT

SELECT
    database_layer,
    ROUND(total_bytes / 1048576.0, 1)    AS size_mb,
    ROUND(total_bytes / 1073741824.0, 3) AS size_gb,
    notes
FROM (VALUES
    ('Operational DB (Business DB)',
     (200*50000 + 50*60000 + 120*50000 + 56*720000 + 68*650000 + 115*3000000),
     'Inkl. CDR als Haupttabelle (329 MB)'),
    ('Data Warehouse (DWH)',
     (135*3000000 + 220*55000 + 115*2000 + 150*3000000),
     'Inkl. Staging Layer (~450 MB)'),
    ('Index Overhead (~20%)',
     CAST(0.2 * (115*3000000 + 135*3000000) AS INTEGER),
     'Indexes auf FK-Spalten')
) AS t(database_layer, total_bytes, notes)

UNION ALL
SELECT
    '═══ GESAMT ═══',
    ROUND((
        200*50000 + 50*60000 + 120*50000 + 56*720000 + 68*650000 + 115*3000000
      + 135*3000000 + 220*55000 + 115*2000 + 150*3000000
      + CAST(0.2*(115*3000000+135*3000000) AS INTEGER)
    ) / 1048576.0, 1),
    ROUND((
        200*50000 + 50*60000 + 120*50000 + 56*720000 + 68*650000 + 115*3000000
      + 135*3000000 + 220*55000 + 115*2000 + 150*3000000
      + CAST(0.2*(115*3000000+135*3000000) AS INTEGER)
    ) / 1073741824.0, 3),
    'Vollständige Plattform (50k Kunden, 1 Jahr)'
ORDER BY size_gb DESC;
