"""
ETL Pipeline

Extract -> Stage -> Validate -> Transform (SCD) -> Load -> Audit

Reads from the operational database and writes to the dimensional
data warehouse using the shared connection layer in db/connection.py.
Both databases are real, persisted DuckDB files using PostgreSQL-compatible SQL.
"""

import sys
import os
import logging
import argparse
from datetime import date, timedelta, datetime
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.connection import get_bdb, get_dwh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ETL")


# ─── DATA QUALITY 

class DataQualityChecker:
    """Validation rules applied to staged event data before warehouse load."""

    RULES = [
        ("not_null_contract_id",  lambda df: df["contract_id"].notna()),
        ("not_null_event_key",    lambda df: df["event_key"].notna()),
        ("not_null_event_datetime", lambda df: df["event_datetime"].notna()),
        ("duration_non_negative", lambda df: df["duration_sec"].fillna(0) >= 0),
        ("data_volume_non_negative", lambda df: df["data_volume_mb"].fillna(0) >= 0),
        ("fraud_score_in_range",  lambda df: df["fraud_score"].between(0, 1)),
        ("cost_non_negative",     lambda df: df["cost"].fillna(0) >= 0),
    ]

    def run(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        report = {}
        mask_valid = pd.Series(True, index=df.index)

        for rule_name, rule_fn in self.RULES:
            result = rule_fn(df)
            n_fail = int((~result).sum())
            report[rule_name] = {"passed": int(result.sum()), "failed": n_fail}
            if n_fail > 0:
                log.warning(f"  Validation rule failed [{rule_name}]: {n_fail} rows")
            mask_valid &= result

        dupes = df.duplicated(subset=["cdr_id"], keep="first")
        n_dupes = int(dupes.sum())
        report["no_duplicate_cdr_id"] = {"passed": len(df) - n_dupes, "failed": n_dupes}
        if n_dupes > 0:
            log.warning(f"  Duplicate cdr_id detected: {n_dupes} rows deduplicated")
        mask_valid &= ~dupes

        valid_df    = df[mask_valid].copy()
        rejected_df = df[~mask_valid].copy()

        pct = 100 * len(valid_df) / len(df) if len(df) else 0
        log.info(f"  Validation: {len(valid_df):,} valid / {len(rejected_df):,} rejected "
                 f"({pct:.1f}% pass rate)")
        return valid_df, rejected_df, report


# ─── SCD TYPE 2 

class SCD2Handler:
    """
    Manages SCD Type 2 versioning for DIM_CUSTOMER.
    Tracked attributes: profession, segment.
    """

    TRACKED_COLS = ["profession", "segment"]

    def process(self, dwh, source_customers: pd.DataFrame, load_date: date) -> dict:
        existing = dwh.read_df("SELECT * FROM dim_customer WHERE is_current = TRUE")
        max_key  = dwh.read_df("SELECT COALESCE(MAX(customer_key), 0) AS m FROM dim_customer").iloc[0]["m"]
        max_key  = int(max_key)

        existing_by_id = existing.set_index("customer_id").to_dict("index") if not existing.empty else {}

        to_close = []
        to_insert = []

        for _, row in source_customers.iterrows():
            cid = row["customer_id"]
            cur = existing_by_id.get(cid)

            if cur is None:
                max_key += 1
                to_insert.append({
                    "customer_key": max_key, "customer_id": cid,
                    "first_name": row["first_name"], "last_name": row["last_name"],
                    "gender": row["gender"], "birth_date": row["birth_date"],
                    "age": row["age"], "profession": row["profession"],
                    "city": row["city"], "country": row["country"],
                    "segment": row["segment"], "customer_status": row["customer_status"],
                    "effective_from": load_date, "effective_to": None, "is_current": True,
                })
                continue

            changed = any(str(cur.get(c)) != str(row[c]) for c in self.TRACKED_COLS)
            if changed:
                to_close.append(cur["customer_key"])
                max_key += 1
                to_insert.append({
                    "customer_key": max_key, "customer_id": cid,
                    "first_name": row["first_name"], "last_name": row["last_name"],
                    "gender": row["gender"], "birth_date": row["birth_date"],
                    "age": row["age"], "profession": row["profession"],
                    "city": row["city"], "country": row["country"],
                    "segment": row["segment"], "customer_status": row["customer_status"],
                    "effective_from": load_date, "effective_to": None, "is_current": True,
                })

        if to_close:
            for key in to_close:
                dwh.execute(
                    "UPDATE dim_customer SET effective_to = ?, is_current = FALSE "
                    "WHERE customer_key = ?",
                    [load_date - timedelta(days=1), int(key)]
                )

        if to_insert:
            ins_df = pd.DataFrame(to_insert)
            dwh.write_df(ins_df, "dim_customer", if_exists="append")

        log.info(f"  SCD2: {len(to_close)} rows closed, {len(to_insert)} rows inserted")
        return {"closed": len(to_close), "inserted": len(to_insert)}


# ─── DIM_TIME GENERATOR 

def generate_dim_time(start: date, end: date) -> pd.DataFrame:
    MONTHS = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    DAYS   = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    holidays = {
        date(2024,1,1), date(2024,1,6), date(2024,4,1), date(2024,5,1),
        date(2024,5,9), date(2024,5,20), date(2024,8,15), date(2024,10,26),
        date(2024,11,1), date(2024,12,8), date(2024,12,25), date(2024,12,26),
    }
    rows = []
    current = start
    while current <= end:
        for hour in (0, 6, 12, 18):
            tod = {0: "Night", 6: "Morning", 12: "Afternoon", 18: "Evening"}[hour]
            rows.append({
                "time_key": int(current.strftime("%Y%m%d")) * 100 + hour,
                "date_val": current, "day": current.day, "day_name": DAYS[current.weekday()],
                "week": current.isocalendar()[1], "week_name": f"W{current.isocalendar()[1]:02d}",
                "month": current.month, "month_name": MONTHS[current.month - 1],
                "quarter": (current.month - 1) // 3 + 1, "year": current.year,
                "is_weekend": current.weekday() >= 5, "holiday_flag": current in holidays,
                "time_of_day": tod, "hour": hour,
            })
        current += timedelta(days=1)
    return pd.DataFrame(rows)


# ─── ETL PIPELINE 

class ETLPipeline:
    """Orchestrates the Extract -> Stage -> Validate -> Transform -> Load sequence."""

    def __init__(self):
        self.dq   = DataQualityChecker()
        self.scd2 = SCD2Handler()
        self.run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def extract(self, bdb, start: date, end: date) -> pd.DataFrame:
        log.info(f"[EXTRACT] {start} to {end}")
        df = bdb.read_df(
            "SELECT * FROM cdr WHERE event_datetime::DATE BETWEEN ? AND ?",
            [start, end]
        )
        log.info(f"  Extracted {len(df):,} rows from operational database")
        return df

    def stage(self, dwh, df: pd.DataFrame) -> None:
        log.info("[STAGE] Writing to stg_cdr")
        if df.empty:
            return
        df = df.copy()
        df["etl_load_date"] = date.today()
        df["etl_status"]    = "PENDING"
        dwh.execute("DELETE FROM stg_cdr")
        dwh.write_df(df, "stg_cdr", if_exists="append")
        log.info(f"  {len(df):,} rows staged")

    def validate(self, dwh) -> pd.DataFrame:
        log.info("[VALIDATE] Running data quality checks")
        staged = dwh.read_df("SELECT * FROM stg_cdr")
        if staged.empty:
            return staged

        valid_df, rejected_df, _ = self.dq.run(staged)
        valid_df["etl_status"]    = "VALID"
        rejected_df["etl_status"] = "REJECTED"

        combined = pd.concat([valid_df, rejected_df], ignore_index=True)
        dwh.execute("DELETE FROM stg_cdr")
        dwh.write_df(combined, "stg_cdr", if_exists="append")
        return valid_df

    def load_dimensions(self, dwh, customers_df: pd.DataFrame,
                        tariffs_df: pd.DataFrame, locations_df: pd.DataFrame,
                        load_date: date) -> None:
        log.info("[TRANSFORM] Updating dimension tables")

        existing = dwh.read_df("SELECT COUNT(*) AS n FROM dim_time").iloc[0]["n"]
        if existing == 0:
            dim_time = generate_dim_time(date(2024, 1, 1), date(2024, 12, 31))
            dwh.write_df(dim_time, "dim_time", if_exists="append")
            log.info(f"  dim_time: {len(dim_time):,} rows generated")

        self.scd2.process(dwh, customers_df, load_date)

        existing_t = dwh.read_df("SELECT tariff_key FROM dim_tariff")
        if existing_t.empty:
            dwh.write_df(tariffs_df, "dim_tariff", if_exists="append")
            log.info(f"  dim_tariff: {len(tariffs_df)} rows loaded")

        existing_l = dwh.read_df("SELECT COUNT(*) AS n FROM dim_location").iloc[0]["n"]
        if existing_l == 0:
            dwh.write_df(locations_df, "dim_location", if_exists="append")
            log.info(f"  dim_location: {len(locations_df):,} rows loaded")

    def load_fact(self, dwh, bdb, valid_df: pd.DataFrame) -> int:
        log.info("[LOAD] Aggregating into fact_usage_events")
        if valid_df.empty:
            return 0

        df = valid_df.copy()
        df["event_datetime"] = pd.to_datetime(df["event_datetime"])
        df["date_str"]  = df["event_datetime"].dt.strftime("%Y%m%d")
        df["hour"]      = df["event_datetime"].dt.hour
        df["hour_bkt"]  = pd.cut(df["hour"], bins=[-1,5,11,17,23], labels=[0,6,12,18]).astype(int)
        df["time_key"]  = df["date_str"].astype(int) * 100 + df["hour_bkt"]

        agg = df.groupby(
            ["contract_id", "time_key", "event_key", "location_id"], as_index=False
        ).agg(
            call_count              = ("event_key", lambda x: int((x.isin([1, 7])).sum())),
            sms_count               = ("event_key", lambda x: int((x == 2).sum())),
            total_call_duration_sec = ("duration_sec", "sum"),
            total_data_volume_mb    = ("data_volume_mb", "sum"),
            revenue_amount          = ("cost", "sum"),
            fraud_score             = ("fraud_score", "max"),
            event_count             = ("cdr_id", "count"),
        )

        # contract -> tariff_id and contract -> customer_id come from the
        # operational database, not the warehouse.
        contract_cust = bdb.read_df(
            "SELECT c.contract_id, c.tariff_id, c.customer_id "
            "FROM contract c"
        ) if bdb.table_exists("contract") else pd.DataFrame()

        if not contract_cust.empty:
            agg = agg.merge(contract_cust, on="contract_id", how="left")
            dim_cust = dwh.read_df("SELECT customer_key, customer_id FROM dim_customer WHERE is_current = TRUE")
            agg = agg.merge(dim_cust, on="customer_id", how="left")
            agg["customer_key"] = agg["customer_key"].fillna(-1).astype(int)
            agg["tariff_key"]   = agg["tariff_id"].fillna(2001).astype(int)
        else:
            agg["customer_key"] = -1
            agg["tariff_key"]   = 2001

        start_key = dwh.read_df(
            "SELECT COALESCE(MAX(usage_event_key), 0) AS m FROM fact_usage_events"
        ).iloc[0]["m"]
        start_key = int(start_key) + 1

        agg["usage_event_key"]       = range(start_key, start_key + len(agg))
        agg["channel_key"]           = 1
        agg["roaming_revenue"]       = 0.0
        agg["international_revenue"] = 0.0
        agg["discount_amount"]       = 0.0
        agg = agg.rename(columns={"location_id": "location_key"})

        fact_cols = ["usage_event_key", "customer_key", "time_key", "tariff_key",
                     "event_key", "channel_key", "location_key", "call_count", "sms_count",
                     "total_call_duration_sec", "total_data_volume_mb", "revenue_amount",
                     "roaming_revenue", "international_revenue", "discount_amount",
                     "fraud_score", "event_count"]
        agg = agg[fact_cols]

        n = dwh.write_df(agg, "fact_usage_events", if_exists="append")
        log.info(f"  Loaded {n:,} fact rows")
        return n

    def audit(self, n_extracted, n_valid, n_fact, start, end) -> dict:
        rejected = n_extracted - n_valid
        log.info("[AUDIT]")
        log.info(f"  run_id:    {self.run_id}")
        log.info(f"  window:    {start} -> {end}")
        log.info(f"  extracted: {n_extracted:,}")
        log.info(f"  valid:     {n_valid:,}")
        log.info(f"  rejected:  {rejected:,}")
        log.info(f"  fact_rows: {n_fact:,}")
        return {"run_id": self.run_id, "extracted": n_extracted,
                "valid": n_valid, "rejected": rejected, "fact_rows": n_fact}

    def run(self, start: date, end: date,
            customers_df: pd.DataFrame, tariffs_df: pd.DataFrame,
            locations_df: pd.DataFrame) -> dict:
        log.info("=" * 60)
        log.info(f"ETL RUN START  [{self.run_id}]  window={start}..{end}")
        log.info("=" * 60)

        with get_bdb() as bdb, get_dwh() as dwh:
            raw_df = self.extract(bdb, start, end)
            n_ext  = len(raw_df)

            self.stage(dwh, raw_df)
            valid_df = self.validate(dwh)
            n_valid  = len(valid_df)

            self.load_dimensions(dwh, customers_df, tariffs_df, locations_df, end)
            n_fact = self.load_fact(dwh, bdb, valid_df)

        result = self.audit(n_ext, n_valid, n_fact, start, end)
        log.info("ETL RUN COMPLETE")
        return result


# ─── FK INTEGRITY VERIFICATION 

def verify_fk_integrity() -> dict:
    log.info("[VERIFY] Foreign key integrity check")
    results = {}
    with get_dwh() as dwh:
        if dwh.table_count("fact_usage_events") == 0:
            log.info("  fact_usage_events is empty — nothing to verify")
            return results

        orphan_time = dwh.read_df(
            "SELECT COUNT(*) AS n FROM fact_usage_events f "
            "WHERE NOT EXISTS (SELECT 1 FROM dim_time t WHERE t.time_key = f.time_key)"
        ).iloc[0]["n"]
        results["orphan_time_keys"] = int(orphan_time)
        log.info(f"  orphan time_key rows: {orphan_time}")

        orphan_cust = dwh.read_df(
            "SELECT COUNT(*) AS n FROM fact_usage_events f "
            "WHERE NOT EXISTS (SELECT 1 FROM dim_customer c WHERE c.customer_key = f.customer_key)"
        ).iloc[0]["n"]
        results["orphan_customer_keys"] = int(orphan_cust)
        log.info(f"  orphan customer_key rows: {orphan_cust}")

    return results


# ─── CLI 

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telecom DWH ETL Pipeline")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-01-07")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    with get_bdb() as bdb:
        customers_df = bdb.read_df("SELECT * FROM customer")
        tariffs_df   = bdb.read_df(
            "SELECT tariff_id AS tariff_key, tariff_id, tariff_name, tariff_type, "
            "monthly_fee, free_minutes, free_sms, data_mb, "
            "o.operator_name, o.country AS operator_country "
            "FROM tariff t JOIN operator o ON o.operator_id = t.operator_id"
        )
        locations_df = bdb.read_df(
            "SELECT location_id AS location_key, location_id, country, region, city, "
            "cell_tower_id, area_type, latitude, longitude FROM location"
        )

    pipeline = ETLPipeline()
    result = pipeline.run(start, end, customers_df, tariffs_df, locations_df)
    verify_fk_integrity()
    print(f"\nResult: {result}")
