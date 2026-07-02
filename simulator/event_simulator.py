"""
Behavioral Event Simulator
===========================
Generates realistic CDR / Usage Events per customer per day.

Design:
  1. For each active contract on a given date:
     - Sample daily event count from segment's Poisson distribution
     - Assign hour based on temporal weights
     - Assign event type based on segment profile
     - Compute revenue based on tariff + event type
  2. Fraud injection: 3% of customers get scenario-based fraud patterns
  3. Output: list of event dicts → Business DB CDR table
"""
import random
import math
import numpy as np
from datetime import date, datetime, timedelta
from simulator.config import (SEGMENTS, EVENT_TYPES, HOUR_WEIGHTS, DOW_WEIGHTS,
                    MONTH_WEIGHTS, FRAUD_SCENARIOS, FRAUD_RATE,
                    N_CUSTOMERS, RANDOM_SEED, SIM_START, SIM_END)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def sample_hour() -> int:
    """Sample hour of day using empirical telecom usage distribution."""
    return random.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]


def sample_duration(mu: float, sigma: float) -> int:
    """LogNormal call duration in seconds."""
    d = int(np.random.lognormal(math.log(mu), sigma))
    return max(1, min(d, 7200))   # cap at 2 hours


def temporal_weight(d: date) -> float:
    """Combined day-of-week × month seasonality weight."""
    return DOW_WEIGHTS[d.weekday()] * MONTH_WEIGHTS[d.month - 1]


def compute_revenue(event_key: int, duration_sec: int,
                    data_mb: float, tariff: dict) -> float:
    """
    Simple revenue calculation:
    - Calls:   per-minute charge if over free_minutes (else 0)
    - Data:    per-MB charge if over free data
    - Billing: monthly_fee chunk
    - Others:  0
    """
    base = tariff.get("monthly_fee", 0) or 0

    if event_key in (1, 7):    # voice calls
        free_min = tariff.get("free_minutes") or 0
        per_min  = 0.10 if tariff.get("tariff_type") == "Prepaid" else 0.05
        minutes  = duration_sec / 60
        excess   = max(0, minutes - free_min / 30)   # rough daily share
        return round(excess * per_min, 4)

    if event_key == 3:          # data session
        free_mb  = tariff.get("data_mb") or 0
        per_mb   = 0.005 if tariff.get("tariff_type") == "Prepaid" else 0.002
        excess   = max(0, data_mb - free_mb / 30)
        return round(excess * per_mb, 4)

    if event_key == 4:          # billing charge
        return round(base / 30, 4)

    return 0.0


# ─── FRAUD INJECTION ──────────────────────────────────────────────────────────

def inject_fraud_events(contract: dict, d: date, locations: list,
                        event_counter: list) -> list[dict]:
    """Generate a fraud scenario event burst for a flagged customer."""
    scenario_name = random.choices(
        list(FRAUD_SCENARIOS.keys()),
        weights=[s["weight"] for s in FRAUD_SCENARIOS.values()],
        k=1
    )[0]
    scenario = FRAUD_SCENARIOS[scenario_name]
    lo, hi = scenario["score_range"]
    fraud_score = round(random.uniform(lo, hi), 2)

    events = []
    base_hour = random.randint(0, 3)   # fraud often at night

    for evt_key in scenario["events"]:
        evt_cfg = EVENT_TYPES[evt_key]
        hour = (base_hour + random.randint(0, 1)) % 24
        minute = random.randint(0, 59)
        second = random.randint(0, 59)
        event_dt = datetime(d.year, d.month, d.day, hour, minute, second)

        dur = sample_duration(15, 0.5) if evt_key == 11 else sample_duration(180, 1.2)
        data_mb = round(np.random.lognormal(math.log(500), 1.0), 2) if evt_key == 3 else 0.0
        loc = random.choice(locations) if locations else {"location_id": 4001}

        event_counter[0] += 1
        tariff_dummy = {"monthly_fee": 29.99, "tariff_type": "Postpaid",
                        "free_minutes": 500, "data_mb": 10240}

        events.append({
            "cdr_id":          event_counter[0],
            "contract_id":     contract["contract_id"],
            "receiver_id":     random.randint(100001, 150000),
            "event_key":       evt_key,
            "event_name":      evt_cfg["name"],
            "event_category":  evt_cfg["category"],
            "event_datetime":  event_dt,
            "duration_sec":    dur,
            "data_volume_mb":  data_mb,
            "location_id":     loc["location_id"],
            "cost":            compute_revenue(evt_key, dur, data_mb, tariff_dummy),
            "fraud_flag":      True,
            "fraud_score":     fraud_score,
            "fraud_scenario":  scenario_name,
            "call_type":       "Outgoing" if evt_key in (1, 7) else "N/A",
        })
    return events


# ─── MAIN SIMULATOR ───────────────────────────────────────────────────────────

def simulate_day(
    d: date,
    contracts: list[dict],
    customers_map: dict,       # customer_id → customer
    tariff_map: dict,          # tariff_id → tariff
    locations: list[dict],
    fraud_set: set,            # set of customer_ids flagged as fraud
    event_counter: list,       # mutable [int] for global ID
) -> list[dict]:
    """
    Simulate all events for one calendar day across all active contracts.
    Returns list of CDR/event rows.
    """
    tw = temporal_weight(d)
    daily_events = []

    for contract in contracts:
        # Active contract check
        cs = contract["start_date"]
        ce = contract["end_date"] or date(9999, 12, 31)
        if not (cs <= d <= ce):
            continue

        cust = customers_map.get(contract["customer_id"])
        if not cust:
            continue

        segment    = cust["segment"]
        seg_cfg    = SEGMENTS[segment]
        tariff     = tariff_map.get(contract["tariff_id"], {})
        is_fraud   = cust["customer_id"] in fraud_set

        # Fraud injection (probabilistic, ~3 days/month for fraud customers)
        if is_fraud and random.random() < 0.30:
            fraud_events = inject_fraud_events(contract, d, locations, event_counter)
            daily_events.extend(fraud_events)
            continue

        # Normal behavior simulation
        lam = seg_cfg["calls_per_day_lambda"] * tw
        n_events = np.random.poisson(lam)

        # Event type weights per segment
        call_events  = [1, 7, 11]
        data_events  = [3]
        sms_events   = [2]
        admin_events = [4, 5, 6, 8, 9, 10]

        event_pool = (
            call_events  * 3 +
            sms_events   * 2 +
            data_events  * 2 +
            admin_events * 1
        )

        for _ in range(n_events):
            evt_key = random.choice(event_pool)
            evt_cfg = EVENT_TYPES[evt_key]

            hour   = sample_hour()
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            event_dt = datetime(d.year, d.month, d.day, hour, minute, second)

            # International call probability
            if evt_key == 1 and random.random() < seg_cfg["intl_call_prob"]:
                evt_key = 7
                evt_cfg = EVENT_TYPES[7]

            # Duration & data
            dur     = sample_duration(seg_cfg["call_duration_mu"],
                                      seg_cfg["call_duration_sigma"])
            if evt_key == 11:
                dur = random.randint(1, 4)   # short call

            data_mb = 0.0
            if evt_key == 3:
                data_mb = round(np.random.lognormal(
                    math.log(seg_cfg["data_mb_per_day_mu"]),
                    seg_cfg["data_mb_per_day_sigma"]), 2)

            loc = random.choice(locations) if locations else {"location_id": 4001}
            cost = compute_revenue(evt_key, dur, data_mb, tariff)

            # Baseline fraud score for non-fraud customers (noise)
            f_score = round(random.uniform(0.0, 0.15), 2)

            event_counter[0] += 1
            daily_events.append({
                "cdr_id":          event_counter[0],
                "contract_id":     contract["contract_id"],
                "receiver_id":     random.randint(100001, 149999),
                "event_key":       evt_key,
                "event_name":      evt_cfg["name"],
                "event_category":  evt_cfg["category"],
                "event_datetime":  event_dt,
                "duration_sec":    dur if evt_key in (1, 7, 11) else 0,
                "data_volume_mb":  data_mb,
                "location_id":     loc["location_id"],
                "cost":            cost,
                "fraud_flag":      False,
                "fraud_score":     f_score,
                "fraud_scenario":  None,
                "call_type":       ("Outgoing" if evt_key in (1, 7) else
                                   "Incoming" if random.random() < 0.4 else "N/A"),
            })

    return daily_events


def run_simulation(customers: list, contracts: list, locations: list,
                   tariffs: list, start: date = SIM_START,
                   end: date = SIM_END) -> list[dict]:
    """
    Full simulation loop over the date range.
    Returns all CDR events (can be millions for full dataset).
    """
    customers_map = {c["customer_id"]: c for c in customers}
    tariff_map    = {t["tariff_id"]: t for t in tariffs}

    # Mark fraud customers
    fraud_count = max(1, int(len(customers) * FRAUD_RATE))
    fraud_set   = set(random.sample([c["customer_id"] for c in customers], fraud_count))

    event_counter = [0]
    all_events = []

    current = start
    day_count = 0
    while current <= end:
        day_events = simulate_day(
            current, contracts, customers_map,
            tariff_map, locations, fraud_set, event_counter
        )
        all_events.extend(day_events)
        current += timedelta(days=1)
        day_count += 1
        if day_count % 30 == 0:
            print(f"  Simulated through {current} — {len(all_events):,} events so far")

    print(f"\nSimulation complete: {len(all_events):,} total events")
    print(f"Fraud customers: {fraud_count} / {len(customers)}")
    return all_events, fraud_set


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from simulator.customer_generator import (generate_customers, generate_contracts,
                                    generate_locations)
    from simulator.config import TARIFFS

    print("Running module self-test (200 customers, January 2024)...")
    custs = generate_customers(200)
    contrs = generate_contracts(custs)
    locs = generate_locations(50)

    events, fraud_set = run_simulation(custs, contrs, locs, TARIFFS,
                                       start=date(2024, 1, 1),
                                       end=date(2024, 1, 31))
    fraud_events = [e for e in events if e["fraud_flag"]]
    print(f"Fraud events: {len(fraud_events)} / {len(events)}")
    print("Event simulator OK")

    import pandas as pd
    df = pd.DataFrame(events)
    df.to_csv("cdr_events.csv", index=False)
    run_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_parquet(f"cdr_{run_date}.parquet", index=False)
    print(f"Saved: cdr_events.csv and cdr_{run_date}.parquet")
