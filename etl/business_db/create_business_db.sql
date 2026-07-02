
--  OPERATIONAL DATABASE (3NF)
--  Telecom Customer Behavior & Fraud Analytics Platform
-- ANSI-compatible SQL — runs on DuckDB and PostgreSQL.

DROP TABLE IF EXISTS cdr;
DROP TABLE IF EXISTS payment;
DROP TABLE IF EXISTS invoice;
DROP TABLE IF EXISTS contract;
DROP TABLE IF EXISTS device;
DROP TABLE IF EXISTS customer;
DROP TABLE IF EXISTS tariff;
DROP TABLE IF EXISTS operator;
DROP TABLE IF EXISTS location;
DROP TABLE IF EXISTS region;
DROP TABLE IF EXISTS event_type;
DROP TABLE IF EXISTS channel;

-- region 
CREATE TABLE region (
    region_id    INTEGER       PRIMARY KEY,
    bundesland   VARCHAR(60)   NOT NULL,
    country      VARCHAR(60)   NOT NULL DEFAULT 'Austria'
);

--  operator 
CREATE TABLE operator (
    operator_id   INTEGER       PRIMARY KEY,
    operator_name VARCHAR(100)  NOT NULL,
    country       VARCHAR(60)   NOT NULL DEFAULT 'Austria'
);

--  tariff 
CREATE TABLE tariff (
    tariff_id      INTEGER       PRIMARY KEY,
    tariff_name    VARCHAR(100)  NOT NULL,
    tariff_type    VARCHAR(20)   NOT NULL CHECK (tariff_type IN ('Prepaid','Postpaid')),
    monthly_fee    DECIMAL(8,2)  NOT NULL,
    free_minutes   INTEGER,
    free_sms       INTEGER,
    data_mb        INTEGER,
    operator_id    INTEGER       NOT NULL REFERENCES operator(operator_id),
    valid_from     DATE          NOT NULL DEFAULT '2024-01-01',
    valid_to       DATE
);

--  customer 
CREATE TABLE customer (
    customer_id     INTEGER       PRIMARY KEY,
    first_name      VARCHAR(80)   NOT NULL,
    last_name       VARCHAR(80)   NOT NULL,
    gender          CHAR(1)       CHECK (gender IN ('M','F','D')),
    birth_date      DATE,
    age             INTEGER,
    profession      VARCHAR(80),
    city            VARCHAR(80),
    country         VARCHAR(60)   NOT NULL DEFAULT 'Austria',
    region_id       INTEGER       REFERENCES region(region_id),
    segment         VARCHAR(20)   NOT NULL
                    CHECK (segment IN ('Budget','Standard','Premium','Business','Senior')),
    customer_status VARCHAR(20)   NOT NULL DEFAULT 'Active',
    created_at      DATE          NOT NULL DEFAULT CURRENT_DATE
);

--  device 
CREATE TABLE device (
    device_id      INTEGER       PRIMARY KEY,
    customer_id    INTEGER       NOT NULL REFERENCES customer(customer_id),
    manufacturer   VARCHAR(60),
    model          VARCHAR(80),
    os_type        VARCHAR(40),
    device_type    VARCHAR(40)   DEFAULT 'Smartphone',
    registered_at  DATE
);

--  contract
CREATE TABLE contract (
    contract_id  INTEGER       PRIMARY KEY,
    customer_id  INTEGER       NOT NULL REFERENCES customer(customer_id),
    tariff_id    INTEGER       NOT NULL REFERENCES tariff(tariff_id),
    start_date   DATE          NOT NULL,
    end_date     DATE,
    status       VARCHAR(20)   NOT NULL DEFAULT 'Active'
                 CHECK (status IN ('Active','Closed','Suspended'))
);

--  event_type 
CREATE TABLE event_type (
    event_key        INTEGER       PRIMARY KEY,
    event_name       VARCHAR(80)   NOT NULL,
    event_category   VARCHAR(40)   NOT NULL,
    is_chargeable    BOOLEAN       NOT NULL DEFAULT TRUE,
    fraud_risk_level VARCHAR(20)   NOT NULL DEFAULT 'Low'
                     CHECK (fraud_risk_level IN ('Low','Medium','High','Critical'))
);

--  channel 
CREATE TABLE channel (
    channel_id    INTEGER       PRIMARY KEY,
    channel_name  VARCHAR(60)   NOT NULL,
    channel_type  VARCHAR(40)   NOT NULL
);

--  location 
CREATE TABLE location (
    location_id   INTEGER       PRIMARY KEY,
    country       VARCHAR(60)   NOT NULL DEFAULT 'Austria',
    region        VARCHAR(60),
    city          VARCHAR(80),
    cell_tower_id VARCHAR(20)   UNIQUE,
    area_type     VARCHAR(20)   CHECK (area_type IN ('Urban','Suburban','Rural')),
    latitude      DECIMAL(9,6),
    longitude     DECIMAL(9,6)
);

-- cdr (core transaction table) 
CREATE TABLE cdr (
    cdr_id          BIGINT        PRIMARY KEY,
    contract_id     INTEGER       NOT NULL REFERENCES contract(contract_id),
    receiver_id     INTEGER,
    event_key       INTEGER       NOT NULL REFERENCES event_type(event_key),
    event_datetime  TIMESTAMP     NOT NULL,
    duration_sec    INTEGER       DEFAULT 0 CHECK (duration_sec >= 0),
    data_volume_mb  DECIMAL(12,4) DEFAULT 0.0,
    location_id     INTEGER       REFERENCES location(location_id),
    cost            DECIMAL(10,4) NOT NULL DEFAULT 0.0,
    call_type       VARCHAR(20)   CHECK (call_type IN ('Outgoing','Incoming','N/A')),
    fraud_flag      BOOLEAN       NOT NULL DEFAULT FALSE,
    fraud_score     DECIMAL(5,2)  NOT NULL DEFAULT 0.0 CHECK (fraud_score BETWEEN 0 AND 1),
    fraud_scenario  VARCHAR(60),
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cdr_contract ON cdr(contract_id);
CREATE INDEX idx_cdr_datetime ON cdr(event_datetime);
CREATE INDEX idx_cdr_event    ON cdr(event_key);
CREATE INDEX idx_cdr_location ON cdr(location_id);

--  payment 
CREATE TABLE payment (
    payment_id   BIGINT        PRIMARY KEY,
    contract_id  INTEGER       NOT NULL REFERENCES contract(contract_id),
    amount       DECIMAL(10,2) NOT NULL CHECK (amount >= 0),
    pay_date     DATE          NOT NULL,
    method       VARCHAR(40)
);

--  invoice 
CREATE TABLE invoice (
    invoice_id     BIGINT        PRIMARY KEY,
    contract_id    INTEGER       NOT NULL REFERENCES contract(contract_id),
    billing_period VARCHAR(7)    NOT NULL,
    total_amount   DECIMAL(10,2) NOT NULL,
    status         VARCHAR(20)   NOT NULL DEFAULT 'Pending'
                   CHECK (status IN ('Pending','Paid','Overdue','Cancelled'))
);

-- Normalization notes:
--   1NF: all attributes atomic, no repeating groups
--   2NF: non-key attributes fully depend on the primary key
--   3NF: no transitive dependencies — operator separated from tariff,
--        region separated from customer, event metadata separated from cdr
