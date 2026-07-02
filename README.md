# Telecom Customer Behavior & Fraud Analytics Platform

A telecom analytics platform that simulates customer activity, stores operational
data in a normalized relational database, processes incremental ETL pipelines,
and loads analytical data into a dimensional data warehouse optimized for
fraud detection and business intelligence.

This project demonstrates the design and implementation of an end-to-end
data platform: behavioral data simulation, operational data modeling,
ETL processing, dimensional modeling, and analytical reporting.

```
python run_pipeline.py
```

That single command generates a synthetic dataset, populates the operational
database, runs the full ETL pipeline into the warehouse, verifies referential
integrity, and prints a sample of the resulting analytics.

---

## Architecture

```
Synthetic Event Generator
          │
          ▼
Operational Database (3NF)
          │
          ▼
ETL Pipeline
 ├── Extract
 ├── Staging
 ├── Validation
 ├── SCD Processing
 └── Load
          │
          ▼
Data Warehouse (Star Schema)
          │
          ▼
Analytics / BI / Fraud Detection
```

The connection layer (`db/connection.py`) abstracts the storage backend.
Supported implementations:

- **DuckDB** — embedded, file-based, zero configuration
- **PostgreSQL** — production deployment via the same connection interface

Every table, query, and stored procedure in this project is written in
ANSI-compatible SQL, so the same schema and ETL logic run unmodified
against either backend.

---

## Features

- Behavioral event simulation across five customer segments with realistic
  call, SMS, and data usage distributions
- Scenario-based fraud injection (SIM box, SIM swap, international fraud,
  premium-rate abuse, roaming abuse) rather than random noise
- Normalized operational database (3NF) with full referential integrity
- Star-schema data warehouse with one fact table and six dimensions
- SCD Type 1 (overwrite) and SCD Type 2 (full history) implementations
- Staging layer with automated data quality validation
- ETL audit logging and post-load foreign key verification
- A single entry point (`run_pipeline.py`) that runs the entire platform

---

## Technology Stack

| Layer            | Technology                          |
|-------------------|--------------------------------------|
| Simulation         | Python, NumPy, Faker                 |
| Operational DB     | DuckDB (PostgreSQL-compatible SQL)   |
| ETL                | Python, pandas                       |
| Data Warehouse     | DuckDB (PostgreSQL-compatible SQL)   |
| Analytics          | SQL                                  |

---

## Project Structure

```
telecom_dwh/
├── run_pipeline.py            # Single entry point — runs the full platform
│
├── db/
│   └── connection.py           # Backend-agnostic connection layer
│
├── simulator/
│   ├── config.py                # Segments, tariffs, event types, fraud scenarios
│   ├── customer_generator.py    # Customers, contracts, devices, locations, payments
│   └── event_simulator.py       # Behavioral event engine and fraud injection
│
├── business_db/
│   └── create_business_db.sql   # Operational schema, 12 tables, 3NF
│
├── dwh/
│   └── create_dwh.sql           # Star schema: 1 fact table, 6 dimensions, staging
│
├── etl/
│   ├── etl_pipeline.py          # Extract → Stage → Validate → Transform → Load
│   └── analytical_queries.sql   # Business queries and ETL verification checks
│
└── docs/
    └── README.md
```

---

## Data Model

### Operational Database (3NF)

Twelve tables capturing the operational reality of a telecom provider:
`customer`, `contract`, `tariff`, `operator`, `device`, `cdr`, `payment`,
`invoice`, `location`, `region`, `event_type`, `channel`.

Design constraints:

- One customer holds exactly one active contract at a time
- One contract maps to exactly one tariff plan
- Each tariff is provided by exactly one operator
- Each CDR (call detail record) links to one contract and one event type
- Fraud labels are attached at the individual event level

### Data Warehouse (Star Schema)

One fact table, `fact_usage_events`, surrounded by six dimensions:
`dim_customer`, `dim_time`, `dim_tariff`, `dim_event`, `dim_channel`,
`dim_location`.

**Grain:** one row per customer, per time bucket, per tariff, per event
type, per channel, per location.

### SCD Strategy

| Dimension       | Type | Rationale                                                        |
|------------------|------|--------------------------------------------------------------------|
| `dim_customer`   | 2    | Profession and segment change over time; historical state matters for accurate fraud attribution |
| `dim_tariff`     | 1    | Plan renames and fee corrections only — current state is sufficient |
| `dim_location`   | 1    | Cell tower coordinates are static reference data                   |
| `dim_event`      | 1    | Event type definitions rarely change                                |
| `dim_channel`    | 1    | Channel names are static reference data                             |
| `dim_time`       | 1    | Generated once, never modified                                      |

---

## ETL Pipeline

The pipeline runs in five stages:

1. **Extract** — pulls CDR records from the operational database for a
   given date window
2. **Stage** — writes raw rows to `stg_cdr` with load metadata
3. **Validate** — applies seven data quality rules (null checks, range
   checks, duplicate detection); rejected rows are quarantined, not dropped
4. **Transform** — updates dimensions, including SCD Type 2 versioning
   for `dim_customer`
5. **Load** — aggregates validated events to the fact grain and writes
   to `fact_usage_events`

Every run logs extracted, valid, rejected, and loaded row counts, and is
followed by a foreign key integrity check against the loaded fact table.

### Schedule

| Process                | Frequency       | Source                | Target                    |
|--------------------------|------------------|-------------------------|------------------------------|
| CDR load                  | Daily            | `cdr`                    | `stg_cdr` → `fact_usage_events` |
| Customer dimension update | Daily            | `customer`                | `dim_customer` (SCD2)        |
| Tariff sync                | Weekly           | `tariff`                  | `dim_tariff` (SCD1)          |
| Location refresh           | On change        | `location`                | `dim_location` (SCD1)        |
| Time dimension extend       | Yearly           | Generated                | `dim_time`                   |

---

## Data Quality

Seven validation rules are applied to every staged batch before it is
eligible for warehouse load:

- Non-null `contract_id`, `event_key`, `event_datetime`
- Non-negative `duration_sec`, `data_volume_mb`, `cost`
- `fraud_score` within `[0, 1]`
- No duplicate `cdr_id`

Rejected rows remain visible in `stg_cdr` with status `REJECTED` rather
than being silently discarded, so failures can be audited.

---

## Fraud Simulation

Fraud is injected through five labeled scenarios rather than random
scoring, so the resulting dataset reflects realistic, learnable patterns:

| Scenario           | Pattern                                            | Score range |
|----------------------|------------------------------------------------------|---------------|
| SIM box                | Burst of short calls from one location, tower change  | 0.75–0.99     |
| International fraud    | Repeated international calls with short duration      | 0.65–0.90     |
| SIM swap                | SIM swap, device change, then international calls     | 0.80–0.99     |
| Premium rate abuse      | Repeated calls paired with billing charges             | 0.60–0.85     |
| Roaming abuse            | Elevated data usage during roaming attach              | 0.55–0.80     |

Approximately 3% of simulated customers are flagged as fraud sources;
their events are drawn from these scenarios instead of normal behavioral
distributions.

---

## Analytical Queries

Four representative queries are provided in `etl/analytical_queries.sql`:

1. Revenue by tariff plan
2. Call frequency by time of day and weekday
3. Data usage by customer segment over time
4. Fraud concentration by region

---

## How to Run

```bash
pip install -r requirements.txt
python run_pipeline.py --customers 2000 --days 30
```

Optional arguments:

- `--customers` — number of customers to simulate (default: 2000)
- `--days` — number of days to simulate (default: 30)
- `--start` — simulation start date (default: 2024-01-01)

The operational database and warehouse are written to `db/business_db.duckdb`
and `db/dwh.duckdb` respectively. Both files persist between runs and can be
inspected independently of the pipeline process, for example:

```python
from db.connection import get_dwh

with get_dwh() as dwh:
    df = dwh.read_df("SELECT * FROM fact_usage_events LIMIT 10")
    print(df)
```

To run the ETL pipeline on its own against existing data:

```bash
python etl/etl_pipeline.py --start 2024-01-01 --end 2024-01-31
```

---

## 🔗 Live Demo

👉 [Telecom DWH Dashboard](https://anniranok.github.io/telecom_dwh/)

---

## Future Improvements

- Additional event types: roaming attach, OTP requests, customer login,
  network type changes, impossible-travel detection
- Feature engineering layer for behavioral and fraud signal extraction
- Fraud detection and churn prediction models trained on simulated data
- Model evaluation layer (ROC-AUC, precision, recall, F1, confusion matrix)
- PostgreSQL deployment via the existing connection abstraction
