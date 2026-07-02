"""
Customer & Contract Generator
Generates demographically realistic customers with behavioral segment assignment.
"""
import random
import numpy as np
from datetime import date, timedelta
from faker import Faker
from simulator.config import (SEGMENTS, BUNDESLAENDER, TARIFFS, N_CUSTOMERS, N_CONTRACTS,
                    SIM_START, SIM_END, RANDOM_SEED)

fake = Faker("de_AT")
Faker.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


def generate_customers(n: int = N_CUSTOMERS) -> list[dict]:
    """Generate n customers with demographic attributes and segment assignment."""
    segment_names = list(SEGMENTS.keys())
    segment_weights = [SEGMENTS[s]["weight"] for s in segment_names]

    customers = []
    for i in range(1, n + 1):
        segment = random.choices(segment_names, weights=segment_weights, k=1)[0]
        seg_cfg = SEGMENTS[segment]
        age = random.randint(*seg_cfg["age_range"])
        birth_date = date.today().replace(year=date.today().year - age)
        region = random.choice(BUNDESLAENDER)

        customers.append({
            "customer_id":  100000 + i,
            "first_name":   fake.first_name(),
            "last_name":    fake.last_name(),
            "gender":       random.choice(["M", "F", "D"]),
            "birth_date":   birth_date,
            "age":          age,
            "profession":   random.choice(seg_cfg["professions"]),
            "city":         fake.city(),
            "country":      "Austria",
            "region_id":    region["region_id"],
            "segment":      segment,
            "customer_status": "Active",
            "effective_from": SIM_START,
            "effective_to":   None,
            "is_current":     True,
        })
    return customers


def generate_contracts(customers: list[dict], n: int = N_CONTRACTS) -> list[dict]:
    """
    Generate contracts. Most customers have 1 contract; some (Premium/Business)
    have 2 contracts over the simulation period (upgrade mid-year).
    """
    tariff_by_segment = {s: SEGMENTS[s]["tariff_ids"] for s in SEGMENTS}
    tariff_map = {t["tariff_id"]: t for t in TARIFFS}

    contracts = []
    contract_id = 500000

    for cust in customers:
        segment = cust["segment"]
        tariff_ids = tariff_by_segment[segment]
        tariff_id = random.choice(tariff_ids)

        # First contract
        start = SIM_START + timedelta(days=random.randint(0, 30))
        end = None
        status = "Active"

        # Premium/Business: ~20% chance of tariff upgrade mid-year
        if segment in ("Premium", "Business") and random.random() < 0.2:
            mid = start + timedelta(days=random.randint(60, 200))
            if mid < SIM_END:
                end = mid
                status = "Closed"

        contracts.append({
            "contract_id": contract_id,
            "customer_id": cust["customer_id"],
            "tariff_id":   tariff_id,
            "start_date":  start,
            "end_date":    end,
            "status":      status,
        })
        contract_id += 1

        # Second contract after upgrade
        if status == "Closed":
            new_tariff = random.choice(tariff_ids)
            contracts.append({
                "contract_id": contract_id,
                "customer_id": cust["customer_id"],
                "tariff_id":   new_tariff,
                "start_date":  end,
                "end_date":    None,
                "status":      "Active",
            })
            contract_id += 1

    return contracts


def generate_devices(customers: list[dict]) -> list[dict]:
    """One device per customer (some switch device = IMEI change)."""
    device_types = ["Smartphone", "Tablet", "USB Modem", "IoT Device"]
    manufacturers = ["Apple", "Samsung", "Huawei", "Xiaomi", "Nokia", "Sony", "Google"]
    os_types = {"Apple": "iOS", "Google": "Android"}

    devices = []
    device_id = 3000
    for cust in customers:
        mfr = random.choice(manufacturers)
        os = os_types.get(mfr, "Android")
        dtype = "Smartphone" if random.random() < 0.80 else random.choice(device_types[1:])
        devices.append({
            "device_id":    device_id,
            "customer_id":  cust["customer_id"],
            "manufacturer": mfr,
            "model":        f"{mfr} {fake.bothify('??##')}",
            "os_type":      os,
            "device_type":  dtype,
            "registered_at": SIM_START + timedelta(days=random.randint(0, 30)),
        })
        device_id += 1
    return devices


def generate_locations(n: int = 2000) -> list[dict]:
    """Generate Austrian cell tower locations with realistic lat/long ranges."""
    # Austria approximate bounding box
    LAT_MIN, LAT_MAX = 46.37, 49.02
    LON_MIN, LON_MAX = 9.53, 17.16

    locations = []
    for i in range(1, n + 1):
        region = random.choice(BUNDESLAENDER)
        locations.append({
            "location_id":  4000 + i,
            "country":      "Austria",
            "region":       region["bundesland"],
            "city":         fake.city(),
            "cell_tower_id": f"CT_{4000 + i}",
            "area_type":    random.choice(["Urban", "Suburban", "Rural"]),
            "latitude":     round(random.uniform(LAT_MIN, LAT_MAX), 4),
            "longitude":    round(random.uniform(LON_MIN, LON_MAX), 4),
        })
    return locations


def generate_payments(contracts: list[dict]) -> list[dict]:
    """Monthly billing payments per active contract."""
    tariff_map = {t["tariff_id"]: t for t in TARIFFS}
    payments = []
    payment_id = 7000000
    methods = ["Credit Card", "Bank Transfer", "Direct Debit", "PayPal", "Cash"]
    method_weights = [0.35, 0.30, 0.25, 0.08, 0.02]

    for contract in contracts:
        tariff = tariff_map.get(contract["tariff_id"], {})
        fee = tariff.get("monthly_fee", 0) or 0
        start = contract["start_date"]
        end = contract["end_date"] or SIM_END

        # Monthly payments
        current = start.replace(day=1)
        while current <= end:
            pay_date = current + timedelta(days=random.randint(1, 5))
            if pay_date > end:
                break
            payments.append({
                "payment_id":  payment_id,
                "contract_id": contract["contract_id"],
                "amount":      round(fee + random.uniform(-0.5, 2.0), 2),
                "pay_date":    pay_date,
                "method":      random.choices(methods, weights=method_weights, k=1)[0],
            })
            payment_id += 1
            # Next month
            month = current.month % 12 + 1
            year = current.year + (1 if current.month == 12 else 0)
            current = current.replace(year=year, month=month)

    return payments


if __name__ == "__main__":
    print("Generating customers...")
    #customers = generate_customers(500)
    DEBUG = True

    customers = generate_customers(500 if DEBUG else N_CUSTOMERS)
    print(f"  {len(customers)} customers")

    contracts = generate_contracts(customers)
    print(f"  {len(contracts)} contracts")

    devices = generate_devices(customers)
    print(f"  {len(devices)} devices")

    locations = generate_locations(50)
    print(f"  {len(locations)} locations")

    payments = generate_payments(contracts)
    print(f"  {len(payments)} payments")
    print("Customer generator OK")
