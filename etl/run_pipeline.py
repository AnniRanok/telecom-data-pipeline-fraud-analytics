"""
run_pipeline.py

Single entry point for the Telecom Behavioral Analytics Platform.

Generates a synthetic telecom dataset, populates the operational database,
runs the ETL pipeline into the dimensional warehouse, verifies referential
integrity, and prints a sample of analytical results.

Usage:
    python run_pipeline.py
    python run_pipeline.py --customers 5000 --days 90
"""

import sys
import os
import argparse
import logging
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from db.connection import get_bdb, get_dwh
from simulator.customer_generator import (
    generate_customers, generate_contracts, generate_devices,
    generate_locations, generate_payments,
)
from simulator.event_simulator import run_simulation
from simulator.config import TARIFFS, OPERATORS, BUNDESLAENDER, EVENT_TYPES, CHANNELS
from etl.etl_pipeline import ETLPipeline, verify_fk_integrity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("PIPELINE")

SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "business_db")
DWH_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "dwh")


# ─── STEP 1: SCHEMA SETUP 

def setup_schemas():
    log.info("STEP 1/6 — Creating database schemas")
    with get_bdb() as bdb:
        sql = open(os.path.join(SCHEMA_DIR, "create_business_db.sql")).read()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                bdb.execute(stmt)
    with get_dwh() as dwh:
        sql = open(os.path.join(DWH_SCHEMA_DIR, "create_dwh.sql")).read()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                dwh.execute(stmt)
    log.info("  Operational database and warehouse schemas ready")


# ─── STEP 2: REFERENCE DATA 

def load_reference_data():
    log.info("STEP 2/6 — Loading reference data (regions, operators, tariffs, lookups)")
    with get_bdb() as bdb:
        bdb.write_df(pd.DataFrame(BUNDESLAENDER), "region", if_exists="append")
        bdb.write_df(pd.DataFrame(OPERATORS), "operator", if_exists="append")
        bdb.write_df(pd.DataFrame(TARIFFS), "tariff", if_exists="append")

        event_rows = [
            {"event_key": k, "event_name": v["name"], "event_category": v["category"],
             "is_chargeable": v["is_chargeable"], "fraud_risk_level": v["fraud_risk"]}
            for k, v in EVENT_TYPES.items()
        ]
        bdb.write_df(pd.DataFrame(event_rows), "event_type", if_exists="append")
        bdb.write_df(pd.DataFrame(CHANNELS), "channel", if_exists="append")

    with get_dwh() as dwh:
        dwh.write_df(pd.DataFrame(event_rows), "dim_event", if_exists="append")
        dwh.write_df(pd.DataFrame(CHANNELS).rename(columns={"channel_id": "channel_key"}),
                    "dim_channel", if_exists="append")
    log.info("  Reference data loaded")


# ─── STEP 3: SYNTHETIC DATASET GENERATION 

def generate_dataset(n_customers: int, start: date, end: date):
    log.info(f"STEP 3/6 — Generating synthetic telecom dataset "
             f"({n_customers:,} customers, {start} to {end})")

    customers = generate_customers(n_customers)
    contracts = generate_contracts(customers)
    devices   = generate_devices(customers)
    locations = generate_locations(2000)
    payments  = generate_payments(contracts)

    log.info(f"  customers: {len(customers):,}  contracts: {len(contracts):,}  "
             f"devices: {len(devices):,}  locations: {len(locations):,}  "
             f"payments: {len(payments):,}")

    log.info("  Simulating behavioral event stream...")
    events, fraud_set = run_simulation(
        customers, contracts, locations, TARIFFS, start=start, end=end
    )
    log.info(f"  events generated: {len(events):,}  flagged accounts: {len(fraud_set)}")

    return customers, contracts, devices, locations, payments, events


# ─── STEP 4: POPULATE OPERATIONAL DATABASE 
def populate_operational_db(customers, contracts, devices, locations, payments, events):
    log.info("STEP 4/6 — Populating operational database")

    cust_df = pd.DataFrame(customers).drop(columns=["effective_from", "effective_to", "is_current"])
    cust_df = cust_df.rename(columns={"region_id": "region_id"})

    cont_df = pd.DataFrame(contracts)
    dev_df  = pd.DataFrame(devices)
    loc_df  = pd.DataFrame(locations)
    pay_df  = pd.DataFrame(payments)

    cdr_cols = ["cdr_id", "contract_id", "receiver_id", "event_key", "event_datetime",
                "duration_sec", "data_volume_mb", "location_id", "cost",
                "call_type", "fraud_flag", "fraud_score", "fraud_scenario"]
    cdr_df = pd.DataFrame(events)[cdr_cols]

    with get_bdb() as bdb:
        bdb.write_df(cust_df, "customer", if_exists="append")
        bdb.write_df(cont_df, "contract", if_exists="append")
        bdb.write_df(dev_df, "device", if_exists="append")
        bdb.write_df(loc_df, "location", if_exists="append")
        bdb.write_df(pay_df, "payment", if_exists="append")
        bdb.write_df(cdr_df, "cdr", if_exists="append")

        counts = {t: bdb.table_count(t) for t in
                  ["customer", "contract", "device", "location", "payment", "cdr"]}
    log.info(f"  Operational database populated: {counts}")
    return counts


# ─── STEP 5: ETL TO WAREHOUSE 

def run_etl(start: date, end: date):
    log.info("STEP 5/6 — Running ETL pipeline into the data warehouse")

    with get_bdb() as bdb:
        customers_df = bdb.read_df("SELECT * FROM customer")
        tariffs_df   = bdb.read_df(
            "SELECT t.tariff_id AS tariff_key, t.tariff_id, t.tariff_name, t.tariff_type, "
            "t.monthly_fee, t.free_minutes, t.free_sms, t.data_mb, "
            "o.operator_name, o.country AS operator_country "
            "FROM tariff t JOIN operator o ON o.operator_id = t.operator_id"
        )
        locations_df = bdb.read_df(
            "SELECT location_id AS location_key, location_id, country, region, city, "
            "cell_tower_id, area_type, latitude, longitude FROM location"
        )

    pipeline = ETLPipeline()
    result = pipeline.run(start, end, customers_df, tariffs_df, locations_df)
    return result


# ─── STEP 6: VERIFY + SAMPLE ANALYTICS 

def verify_and_report():
    log.info("STEP 6/6 — Verifying integrity and sampling analytics")
    fk_results = verify_fk_integrity()

    with get_dwh() as dwh:
        if dwh.table_count("fact_usage_events") == 0:
            log.warning("  fact_usage_events is empty — skipping analytics sample")
            return fk_results

        log.info("\n  Revenue by tariff plan:")
        top_tariffs = dwh.read_df(
            "SELECT t.tariff_name, ROUND(SUM(f.revenue_amount), 2) AS revenue "
            "FROM fact_usage_events f JOIN dim_tariff t ON t.tariff_key = f.tariff_key "
            "GROUP BY t.tariff_name ORDER BY revenue DESC LIMIT 5"
        )
        for _, row in top_tariffs.iterrows():
            log.info(f"    {row['tariff_name']:<20} EUR {row['revenue']:,.2f}")

        log.info("\n  Fraud score distribution:")
        fraud_dist = dwh.read_df(
            "SELECT CASE WHEN fraud_score < 0.3 THEN 'Low' "
            "            WHEN fraud_score < 0.6 THEN 'Medium' "
            "            WHEN fraud_score < 0.8 THEN 'High' "
            "            ELSE 'Critical' END AS risk_level, "
            "       COUNT(*) AS n_events "
            "FROM fact_usage_events GROUP BY 1 ORDER BY 1"
        )
        for _, row in fraud_dist.iterrows():
            log.info(f"    {row['risk_level']:<10} {row['n_events']:,} events")

    return fk_results


# ─── MAIN 

def main():
    parser = argparse.ArgumentParser(description="Telecom Behavioral Analytics Platform — full pipeline")
    parser.add_argument("--customers", type=int, default=2000, help="Number of customers to simulate")
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--start", default="2024-01-01", help="Simulation start date (YYYY-MM-DD)")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = start + timedelta(days=args.days - 1)

    log.info("=" * 64)
    log.info("TELECOM BEHAVIORAL ANALYTICS PLATFORM — PIPELINE RUN")
    log.info("=" * 64)

    setup_schemas()
    load_reference_data()
    customers, contracts, devices, locations, payments, events = generate_dataset(
        args.customers, start, end
    )
    populate_operational_db(customers, contracts, devices, locations, payments, events)
    etl_result = run_etl(start, end)
    verify_and_report()

    log.info("=" * 64)
    log.info("PIPELINE COMPLETE")
    log.info(f"  ETL summary: {etl_result}")
    log.info("=" * 64)


if __name__ == "__main__":
    main()
