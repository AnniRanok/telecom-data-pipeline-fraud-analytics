"""
Data Quality Runner

Executes all DQ checks from etl/data_quality/ against the real databases.
Called automatically by run_pipeline.py after each ETL load.

Returns a structured results dict suitable for logging and audit.
"""

import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from db.connection import get_bdb, get_dwh

log = logging.getLogger("DQ")


# ── Individual check functions 

def check_referential_integrity(dwh, bdb) -> list[dict]:
    """FK orphan checks: all FACT → DIM + operational FK chains."""
    checks = [
        ("RI-01", "FACT → DIM_CUSTOMER",
         "SELECT COUNT(*) AS n FROM fact_usage_events f "
         "WHERE NOT EXISTS (SELECT 1 FROM dim_customer c WHERE c.customer_key = f.customer_key)",
         dwh),
        ("RI-02", "FACT → DIM_TIME",
         "SELECT COUNT(*) AS n FROM fact_usage_events f "
         "WHERE NOT EXISTS (SELECT 1 FROM dim_time t WHERE t.time_key = f.time_key)",
         dwh),
        ("RI-03", "FACT → DIM_TARIFF",
         "SELECT COUNT(*) AS n FROM fact_usage_events f "
         "WHERE NOT EXISTS (SELECT 1 FROM dim_tariff t WHERE t.tariff_key = f.tariff_key)",
         dwh),
        ("RI-04", "FACT → DIM_EVENT",
         "SELECT COUNT(*) AS n FROM fact_usage_events f "
         "WHERE NOT EXISTS (SELECT 1 FROM dim_event e WHERE e.event_key = f.event_key)",
         dwh),
        ("RI-05", "FACT → DIM_CHANNEL",
         "SELECT COUNT(*) AS n FROM fact_usage_events f "
         "WHERE NOT EXISTS (SELECT 1 FROM dim_channel c WHERE c.channel_key = f.channel_key)",
         dwh),
        ("RI-06", "FACT → DIM_LOCATION",
         "SELECT COUNT(*) AS n FROM fact_usage_events f "
         "WHERE NOT EXISTS (SELECT 1 FROM dim_location l WHERE l.location_key = f.location_key)",
         dwh),
        ("RI-07", "PAYMENT → INVOICE",
         "SELECT COUNT(*) AS n FROM payment p "
         "WHERE NOT EXISTS (SELECT 1 FROM invoice i WHERE i.invoice_id = p.invoice_id)",
         bdb),
        ("RI-08", "DEVICE → CUSTOMER",
         "SELECT COUNT(*) AS n FROM device d "
         "WHERE NOT EXISTS (SELECT 1 FROM customer c WHERE c.customer_id = d.customer_id)",
         bdb),
        ("RI-09", "CDR → CONTRACT",
         "SELECT COUNT(*) AS n FROM cdr c "
         "WHERE NOT EXISTS (SELECT 1 FROM contract ct WHERE ct.contract_id = c.contract_id)",
         bdb),
        ("RI-10", "INVOICE → CONTRACT",
         "SELECT COUNT(*) AS n FROM invoice i "
         "WHERE NOT EXISTS (SELECT 1 FROM contract ct WHERE ct.contract_id = i.contract_id)",
         bdb),
    ]

    results = []
    for rule_id, name, sql, db in checks:
        n = int(db.read_df(sql).iloc[0]["n"])
        status = "PASS" if n == 0 else "FAIL"
        results.append({"rule_id": rule_id, "check": name, "failed_rows": n, "status": status})
    return results


def check_data_quality(dwh, bdb) -> list[dict]:
    """Null checks, range checks, format checks on staging + operational DB."""
    checks_stg = [
        ("DQ-01", "NULL contract_id",         "SELECT COUNT(*) AS n FROM stg_cdr WHERE contract_id IS NULL"),
        ("DQ-02", "NULL event_key",            "SELECT COUNT(*) AS n FROM stg_cdr WHERE event_key IS NULL"),
        ("DQ-03", "NULL event_datetime",       "SELECT COUNT(*) AS n FROM stg_cdr WHERE event_datetime IS NULL"),
        ("DQ-04", "duration_sec < 0",          "SELECT COUNT(*) AS n FROM stg_cdr WHERE duration_sec < 0"),
        ("DQ-05", "data_volume_mb < 0",        "SELECT COUNT(*) AS n FROM stg_cdr WHERE data_volume_mb < 0"),
        ("DQ-06", "fraud_score out of [0,1]",  "SELECT COUNT(*) AS n FROM stg_cdr WHERE fraud_score < 0 OR fraud_score > 1"),
        ("DQ-07", "cost < 0",                  "SELECT COUNT(*) AS n FROM stg_cdr WHERE cost < 0"),
        ("DQ-08", "Duplicate cdr_id",          "SELECT COUNT(*) - COUNT(DISTINCT cdr_id) AS n FROM stg_cdr"),
        ("DQ-09", "event_datetime in future",  "SELECT COUNT(*) AS n FROM stg_cdr WHERE CAST(event_datetime AS DATE) > CURRENT_DATE"),
    ]

    checks_biz = [
        ("DQ-11", "Customer NULL name",        "SELECT COUNT(*) AS n FROM customer WHERE first_name IS NULL OR last_name IS NULL"),
        ("DQ-12", "Invalid segment",           "SELECT COUNT(*) AS n FROM customer WHERE segment NOT IN ('Budget','Standard','Premium','Business','Senior')"),
        ("DQ-13", "Contract end < start",      "SELECT COUNT(*) AS n FROM contract WHERE end_date IS NOT NULL AND end_date <= start_date"),
        ("DQ-14", "Tariff fee < 0",            "SELECT COUNT(*) AS n FROM tariff WHERE monthly_fee < 0"),
        ("DQ-15", "Invoice amount <= 0",       "SELECT COUNT(*) AS n FROM invoice WHERE total_amount <= 0"),
    ]

    checks_dwh = [
        ("DQ-18", "SCD2 duplicate current",
         "SELECT COUNT(*) AS n FROM (SELECT customer_id FROM dim_customer "
         "WHERE is_current=TRUE GROUP BY customer_id HAVING COUNT(*)>1) s"),
        ("DQ-19", "SCD2 date range invalid",
         "SELECT COUNT(*) AS n FROM dim_customer "
         "WHERE effective_to IS NOT NULL AND effective_from > effective_to"),
        ("DQ-21", "FACT fraud_score out of [0,1]",
         "SELECT COUNT(*) AS n FROM fact_usage_events WHERE fraud_score < 0 OR fraud_score > 1"),
        ("DQ-22", "FACT negative measures",
         "SELECT COUNT(*) AS n FROM fact_usage_events "
         "WHERE call_count<0 OR sms_count<0 OR revenue_amount<0 OR event_count<0"),
    ]

    results = []
    for rule_id, name, sql in checks_stg:
        n = int(dwh.read_df(sql).iloc[0]["n"])
        results.append({"rule_id": rule_id, "check": name, "failed_rows": n,
                        "status": "PASS" if n == 0 else "FAIL"})

    for rule_id, name, sql in checks_biz:
        n = int(bdb.read_df(sql).iloc[0]["n"])
        results.append({"rule_id": rule_id, "check": name, "failed_rows": n,
                        "status": "PASS" if n == 0 else "FAIL"})

    for rule_id, name, sql in checks_dwh:
        n = int(dwh.read_df(sql).iloc[0]["n"])
        results.append({"rule_id": rule_id, "check": name, "failed_rows": n,
                        "status": "PASS" if n == 0 else "FAIL"})

    return results


def check_business_rules(dwh, bdb) -> list[dict]:
    """Domain-specific business constraint checks."""
    checks = [
        ("BR-01", "Customer > 1 active contract",
         "SELECT COUNT(*) AS n FROM ("
         "SELECT customer_id FROM contract WHERE status='Active' "
         "GROUP BY customer_id HAVING COUNT(*)>1) s",
         bdb),
        ("BR-03", "Closed contract without end_date",
         "SELECT COUNT(*) AS n FROM contract WHERE status='Closed' AND end_date IS NULL",
         bdb),
        ("BR-05", "Invalid tariff_type",
         "SELECT COUNT(*) AS n FROM tariff WHERE tariff_type NOT IN ('Prepaid','Postpaid')",
         bdb),
        ("BR-09", "High fraud_score without fraud_flag",
         "SELECT COUNT(*) AS n FROM cdr WHERE fraud_score > 0.60 AND fraud_flag = FALSE",
         bdb),
        ("BR-10", "Invoice for missing contract",
         "SELECT COUNT(*) AS n FROM invoice i "
         "LEFT JOIN contract ct ON ct.contract_id=i.contract_id WHERE ct.contract_id IS NULL",
         bdb),
        ("BR-11", "Payment without valid invoice",
         "SELECT COUNT(*) AS n FROM payment p "
         "LEFT JOIN invoice i ON i.invoice_id=p.invoice_id WHERE i.invoice_id IS NULL",
         bdb),
        ("BR-13", "Duplicate fact grain",
         "SELECT COUNT(*) AS n FROM ("
         "SELECT customer_key,time_key,tariff_key,event_key,channel_key,location_key "
         "FROM fact_usage_events "
         "GROUP BY customer_key,time_key,tariff_key,event_key,channel_key,location_key "
         "HAVING COUNT(*)>1) s",
         dwh),
        ("BR-14", "DIM_CUSTOMER N/A placeholder missing",
         "SELECT CASE WHEN COUNT(*)=0 THEN 1 ELSE 0 END AS n "
         "FROM dim_customer WHERE customer_key=-1",
         dwh),
    ]

    results = []
    for rule_id, name, sql, db in checks:
        n = int(db.read_df(sql).iloc[0]["n"])
        results.append({"rule_id": rule_id, "check": name, "failed_rows": n,
                        "status": "PASS" if n == 0 else "WARN"})
    return results


def check_row_counts(dwh, bdb) -> dict:
    """Row count reconciliation across all layers."""
    biz_counts = {}
    for t in ["customer", "contract", "cdr", "invoice", "payment",
              "device", "location", "tariff", "operator", "region",
              "event_type", "channel"]:
        biz_counts[t] = bdb.table_count(t)

    dwh_counts = {}
    for t in ["dim_customer", "dim_time", "dim_tariff", "dim_event",
              "dim_channel", "dim_location", "fact_usage_events", "stg_cdr"]:
        dwh_counts[t] = dwh.table_count(t)

    stg_valid = int(dwh.read_df(
        "SELECT COUNT(*) AS n FROM stg_cdr WHERE etl_status='VALID'"
    ).iloc[0]["n"])
    stg_rejected = int(dwh.read_df(
        "SELECT COUNT(*) AS n FROM stg_cdr WHERE etl_status='REJECTED'"
    ).iloc[0]["n"])

    return {
        "business_db": biz_counts,
        "dwh": dwh_counts,
        "staging": {"valid": stg_valid, "rejected": stg_rejected,
                    "total": dwh_counts["stg_cdr"],
                    "pass_rate_pct": round(100 * stg_valid / dwh_counts["stg_cdr"], 2)
                    if dwh_counts["stg_cdr"] > 0 else 0.0},
    }


# ── Master runner 

def run_dq_checks() -> dict:
    """
    Run all DQ checks and return structured results.
    Called automatically from run_pipeline.py Step 6.

    Returns dict with keys: ri, dq, br, counts, summary, timestamp
    """
    log.info("    Running referential integrity checks...")
    with get_bdb() as bdb, get_dwh() as dwh:

        ri_results = check_referential_integrity(dwh, bdb)
        dq_results = check_data_quality(dwh, bdb)
        br_results = check_business_rules(dwh, bdb)
        counts     = check_row_counts(dwh, bdb)

    # ── Log results 
    all_checks = ri_results + dq_results + br_results
    passed  = sum(1 for c in all_checks if c["status"] == "PASS")
    failed  = sum(1 for c in all_checks if c["status"] == "FAIL")
    warned  = sum(1 for c in all_checks if c["status"] == "WARN")
    total   = len(all_checks)

    log.info(f"    DQ summary: {passed}/{total} PASS  |  "
             f"{failed} FAIL  |  {warned} WARN")

    if failed > 0:
        log.warning("    ─── FAILED CHECKS ───────────────────────────────")
        for c in all_checks:
            if c["status"] == "FAIL":
                log.warning(f"    ✗ [{c['rule_id']}] {c['check']} "
                            f"— {c['failed_rows']:,} rows affected")

    if warned > 0:
        log.info("    ─── WARNINGS ────────────────────────────────────")
        for c in all_checks:
            if c["status"] == "WARN":
                log.info(f"    ⚠ [{c['rule_id']}] {c['check']} "
                         f"— {c['failed_rows']:,} rows")

    if failed == 0 and warned == 0:
        log.info("    ✓ All DQ checks passed — data is consistent")

    # ── Row count summary 
    log.info("    ─── Row counts ──────────────────────────────────")
    biz = counts["business_db"]
    dwh = counts["dwh"]
    stg = counts["staging"]
    log.info(f"    {'Table':<28} {'Biz DB':>10}  {'DWH':>10}")
    log.info(f"    {'─'*50}")
    log.info(f"    {'customer / dim_customer':<28} {biz['customer']:>10,}  {dwh['dim_customer']:>10,}")
    log.info(f"    {'contract':<28} {biz['contract']:>10,}  {'—':>10}")
    log.info(f"    {'cdr → fact_usage_events':<28} {biz['cdr']:>10,}  {dwh['fact_usage_events']:>10,}")
    log.info(f"    {'invoice':<28} {biz['invoice']:>10,}  {'—':>10}")
    log.info(f"    {'payment':<28} {biz['payment']:>10,}  {'—':>10}")
    log.info(f"    {'stg_cdr VALID / REJECTED':<28} {stg['valid']:>10,}  {stg['rejected']:>10,}")
    log.info(f"    {'Staging pass rate':<28} {stg['pass_rate_pct']:>9.1f}%")

    return {
        "timestamp":   datetime.now().isoformat(),
        "ri":          ri_results,
        "dq":          dq_results,
        "br":          br_results,
        "counts":      counts,
        "summary": {
            "total":   total,
            "passed":  passed,
            "failed":  failed,
            "warned":  warned,
            "overall": "PASS" if failed == 0 else "FAIL",
        },
    }


# ── CLI 

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log.info("Running all DQ checks manually...")
    results = run_dq_checks()
    log.info(f"Overall status: {results['summary']['overall']}")
