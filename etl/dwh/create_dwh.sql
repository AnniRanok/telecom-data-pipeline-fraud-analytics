
--  DATA WAREHOUSE (STAR SCHEMA)
--  Telecom Customer Behavior & Fraud Analytics Platform
-- ANSI-compatible SQL — runs on DuckDB and PostgreSQL .

DROP TABLE IF EXISTS fact_usage_events;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_time;
DROP TABLE IF EXISTS dim_tariff;
DROP TABLE IF EXISTS dim_event;
DROP TABLE IF EXISTS dim_channel;
DROP TABLE IF EXISTS dim_location;
DROP TABLE IF EXISTS stg_cdr;


--  STAGING LAYER

CREATE TABLE stg_cdr (
    cdr_id          BIGINT,
    contract_id     INTEGER,
    receiver_id     INTEGER,
    event_key       INTEGER,
    event_datetime  TIMESTAMP,
    duration_sec    INTEGER,
    data_volume_mb  DECIMAL(12,4),
    location_id     INTEGER,
    cost            DECIMAL(10,4),
    call_type       VARCHAR(20),
    fraud_flag      BOOLEAN,
    fraud_score     DECIMAL(5,2),
    fraud_scenario  VARCHAR(60),
    created_at      TIMESTAMP,
    etl_load_date   DATE,
    etl_status      VARCHAR(20)
);


--  DIM_TIME — SCD Type 1 (generated, immutable after load)

CREATE TABLE dim_time (
    time_key      INTEGER       PRIMARY KEY,
    date_val      DATE          NOT NULL,
    day           INTEGER       NOT NULL,
    day_name      VARCHAR(15)   NOT NULL,
    week          INTEGER       NOT NULL,
    week_name     VARCHAR(10),
    month         INTEGER       NOT NULL,
    month_name    VARCHAR(15)   NOT NULL,
    quarter       INTEGER       NOT NULL,
    year          INTEGER       NOT NULL,
    is_weekend    BOOLEAN       NOT NULL,
    holiday_flag  BOOLEAN       NOT NULL DEFAULT FALSE,
    time_of_day   VARCHAR(15)   NOT NULL,
    hour          INTEGER       NOT NULL DEFAULT 0
);


--  DIM_CUSTOMER — SCD Type 2 (tracks profession and segment history)

CREATE TABLE dim_customer (
    customer_key    BIGINT        PRIMARY KEY,
    customer_id     INTEGER       NOT NULL,
    first_name      VARCHAR(80),
    last_name       VARCHAR(80),
    gender          CHAR(1),
    birth_date      DATE,
    age             INTEGER,
    profession      VARCHAR(80),
    city            VARCHAR(80),
    country         VARCHAR(60),
    segment         VARCHAR(20),
    customer_status VARCHAR(20),
    effective_from  DATE          NOT NULL,
    effective_to    DATE,
    is_current      BOOLEAN       NOT NULL DEFAULT TRUE
);

INSERT INTO dim_customer
  (customer_key, customer_id, first_name, last_name, gender,
   birth_date, age, profession, city, country, segment, customer_status,
   effective_from, effective_to, is_current)
VALUES
  (-1, -1, 'Unknown', 'Unknown', 'D', NULL, NULL, 'Unknown', 'Unknown',
   'Unknown', 'Unknown', 'Unknown', '2000-01-01', NULL, TRUE);


--  DIM_TARIFF — SCD Type 1 (overwrite on rename / fee correction)

CREATE TABLE dim_tariff (
    tariff_key       INTEGER       PRIMARY KEY,
    tariff_id        INTEGER       NOT NULL,
    tariff_name      VARCHAR(100)  NOT NULL,
    tariff_type      VARCHAR(20)   NOT NULL,
    monthly_fee      DECIMAL(8,2)  NOT NULL,
    free_minutes     INTEGER,
    free_sms         INTEGER,
    data_mb          INTEGER,
    operator_name    VARCHAR(100),
    operator_country VARCHAR(60)
);


--  DIM_EVENT — SCD Type 1

CREATE TABLE dim_event (
    event_key        INTEGER       PRIMARY KEY,
    event_name       VARCHAR(80)   NOT NULL,
    event_category   VARCHAR(40)   NOT NULL,
    is_chargeable    BOOLEAN       NOT NULL DEFAULT TRUE,
    fraud_risk_level VARCHAR(20)   NOT NULL DEFAULT 'Low'
);


--  DIM_CHANNEL — SCD Type 1

CREATE TABLE dim_channel (
    channel_key   INTEGER       PRIMARY KEY,
    channel_name  VARCHAR(60)   NOT NULL,
    channel_type  VARCHAR(40)   NOT NULL
);


--  DIM_LOCATION — SCD Type 1

CREATE TABLE dim_location (
    location_key   INTEGER       PRIMARY KEY,
    location_id    INTEGER       NOT NULL,
    country        VARCHAR(60),
    region         VARCHAR(60),
    city           VARCHAR(80),
    cell_tower_id  VARCHAR(20),
    area_type      VARCHAR(20),
    latitude       DECIMAL(10,6),
    longitude      DECIMAL(10,6)
);


--  FACT_USAGE_EVENTS
--  Grain: one row per customer, per time bucket, per tariff, per event type, per channel, per location

CREATE TABLE fact_usage_events (
    usage_event_key       BIGINT        PRIMARY KEY,
    customer_key           BIGINT        NOT NULL REFERENCES dim_customer(customer_key),
    time_key                INTEGER       NOT NULL REFERENCES dim_time(time_key),
    tariff_key              INTEGER       NOT NULL REFERENCES dim_tariff(tariff_key),
    event_key                INTEGER       NOT NULL REFERENCES dim_event(event_key),
    channel_key              INTEGER       NOT NULL REFERENCES dim_channel(channel_key),
    location_key             INTEGER       NOT NULL REFERENCES dim_location(location_key),
    call_count               INTEGER       NOT NULL DEFAULT 0,
    sms_count                INTEGER       NOT NULL DEFAULT 0,
    total_call_duration_sec  INTEGER       NOT NULL DEFAULT 0,
    total_data_volume_mb     DECIMAL(18,2) NOT NULL DEFAULT 0.0,
    revenue_amount           DECIMAL(18,2) NOT NULL DEFAULT 0.0,
    roaming_revenue          DECIMAL(18,2) NOT NULL DEFAULT 0.0,
    international_revenue    DECIMAL(18,2) NOT NULL DEFAULT 0.0,
    discount_amount          DECIMAL(18,2) NOT NULL DEFAULT 0.0,
    fraud_score               DECIMAL(5,2)  NOT NULL DEFAULT 0.0,
    event_count               INTEGER       NOT NULL DEFAULT 1
);

CREATE INDEX idx_fact_customer ON fact_usage_events(customer_key);
CREATE INDEX idx_fact_time     ON fact_usage_events(time_key);
CREATE INDEX idx_fact_tariff   ON fact_usage_events(tariff_key);
CREATE INDEX idx_fact_event    ON fact_usage_events(event_key);
CREATE INDEX idx_fact_location ON fact_usage_events(location_key);
