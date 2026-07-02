"""
Telecom Event Simulation Engine

Configuration & Constants

The simulator generates realistic telecom events by modeling customer behavior,
temporal usage patterns, mobility, tariff plans, and fraud scenarios.
The generated event stream serves as the operational data source for the
Business Database and the Data Warehouse.
"""

from datetime import date

# ─── SIMULATION PARAMETERS 
SIM_START        = date(2024, 1, 1)
SIM_END          = date(2024, 12, 31)
N_CUSTOMERS      = 50_000
N_CONTRACTS      = 60_000      # some customers have 2 contracts over the year
N_OPERATORS      = 3
N_LOCATIONS      = 2_000       # cell towers across Austria
FRAUD_RATE       = 0.03        # 3% of customers are fraud-injected

RANDOM_SEED      = 42

# ─── AUSTRIAN REGIONS 
BUNDESLAENDER = [
    {"region_id": 1,  "bundesland": "Wien",             "country": "Austria"},
    {"region_id": 2,  "bundesland": "Niederösterreich", "country": "Austria"},
    {"region_id": 3,  "bundesland": "Oberösterreich",   "country": "Austria"},
    {"region_id": 4,  "bundesland": "Steiermark",       "country": "Austria"},
    {"region_id": 5,  "bundesland": "Tirol",            "country": "Austria"},
    {"region_id": 6,  "bundesland": "Salzburg",         "country": "Austria"},
    {"region_id": 7,  "bundesland": "Kärnten",          "country": "Austria"},
    {"region_id": 8,  "bundesland": "Vorarlberg",       "country": "Austria"},
    {"region_id": 9,  "bundesland": "Burgenland",       "country": "Austria"},
]

# ─── TARIFF PLANS 
TARIFFS = [
    {"tariff_id": 2001, "tariff_name": "Budget Talk",    "tariff_type": "Prepaid",  "monthly_fee": 9.99,  "free_minutes": 100, "free_sms": 50,       "data_mb": 1024,      "operator_id": 1},
    {"tariff_id": 2002, "tariff_name": "Standard Plus",  "tariff_type": "Postpaid", "monthly_fee": 29.99, "free_minutes": 500, "free_sms": 500,       "data_mb": 10240,     "operator_id": 1},
    {"tariff_id": 2003, "tariff_name": "Premium Max",    "tariff_type": "Postpaid", "monthly_fee": 59.99, "free_minutes": None,"free_sms": None,      "data_mb": None,      "operator_id": 2},
    {"tariff_id": 2004, "tariff_name": "Business Pro",   "tariff_type": "Postpaid", "monthly_fee": 89.99, "free_minutes": None,"free_sms": None,      "data_mb": None,      "operator_id": 2},
    {"tariff_id": 2005, "tariff_name": "Youth Flex",     "tariff_type": "Prepaid",  "monthly_fee": 14.99, "free_minutes": 200, "free_sms": 200,       "data_mb": 5120,      "operator_id": 3},
    {"tariff_id": 2006, "tariff_name": "Roamer+",        "tariff_type": "Postpaid", "monthly_fee": 49.99, "free_minutes": 300, "free_sms": 100,       "data_mb": 8192,      "operator_id": 3},
    {"tariff_id": 2007, "tariff_name": "Data Only",      "tariff_type": "Postpaid", "monthly_fee": 19.99, "free_minutes": 0,   "free_sms": 0,         "data_mb": 51200,     "operator_id": 1},
    {"tariff_id": 2008, "tariff_name": "SeniorCare",     "tariff_type": "Prepaid",  "monthly_fee": 7.99,  "free_minutes": 60,  "free_sms": 30,        "data_mb": 512,       "operator_id": 2},
    {"tariff_id": 2009, "tariff_name": "Family Share",   "tariff_type": "Postpaid", "monthly_fee": 39.99, "free_minutes": 1000,"free_sms": 1000,      "data_mb": 20480,     "operator_id": 3},
    {"tariff_id": 2010, "tariff_name": "Night Owl",      "tariff_type": "Prepaid",  "monthly_fee": 12.99, "free_minutes": 150, "free_sms": 150,       "data_mb": 3072,      "operator_id": 1},
]

# ─── OPERATORS 
OPERATORS = [
    {"operator_id": 1, "operator_name": "AustriaNet",  "country": "Austria"},
    {"operator_id": 2, "operator_name": "AlpineMobile","country": "Austria"},
    {"operator_id": 3, "operator_name": "ViennaCell",  "country": "Austria"},
]

# ─── CUSTOMER SEGMENTS with behavioral profiles 
# Each segment drives usage simulation
SEGMENTS = {
    "Budget": {
        "weight": 0.30,
        "tariff_ids": [2001, 2010],
        "calls_per_day_lambda": 3.0,       # Poisson λ
        "call_duration_mu": 90,            # LogNormal μ (seconds)
        "call_duration_sigma": 1.2,
        "sms_per_day_lambda": 4.0,
        "data_mb_per_day_mu": 50,
        "data_mb_per_day_sigma": 0.8,
        "intl_call_prob": 0.02,
        "fraud_multiplier": 1.5,
        "age_range": (18, 45),
        "professions": ["Student", "Worker", "Unemployed"],
    },
    "Standard": {
        "weight": 0.35,
        "tariff_ids": [2002, 2005, 2009],
        "calls_per_day_lambda": 5.0,
        "call_duration_mu": 180,
        "call_duration_sigma": 1.4,
        "sms_per_day_lambda": 3.0,
        "data_mb_per_day_mu": 500,
        "data_mb_per_day_sigma": 1.0,
        "intl_call_prob": 0.05,
        "fraud_multiplier": 1.0,
        "age_range": (25, 60),
        "professions": ["Employee", "Manager", "Teacher", "Engineer"],
    },
    "Premium": {
        "weight": 0.20,
        "tariff_ids": [2003, 2006],
        "calls_per_day_lambda": 4.0,
        "call_duration_mu": 300,
        "call_duration_sigma": 1.5,
        "sms_per_day_lambda": 2.0,
        "data_mb_per_day_mu": 2000,
        "data_mb_per_day_sigma": 1.2,
        "intl_call_prob": 0.15,
        "fraud_multiplier": 0.5,
        "age_range": (30, 65),
        "professions": ["Doctor", "Lawyer", "Executive", "Consultant"],
    },
    "Business": {
        "weight": 0.10,
        "tariff_ids": [2004, 2007],
        "calls_per_day_lambda": 15.0,
        "call_duration_mu": 240,
        "call_duration_sigma": 1.3,
        "sms_per_day_lambda": 5.0,
        "data_mb_per_day_mu": 5000,
        "data_mb_per_day_sigma": 1.5,
        "intl_call_prob": 0.25,
        "fraud_multiplier": 0.3,
        "age_range": (28, 60),
        "professions": ["CEO", "Sales Manager", "Analyst", "Consultant"],
    },
    "Senior": {
        "weight": 0.05,
        "tariff_ids": [2008],
        "calls_per_day_lambda": 1.5,
        "call_duration_mu": 200,
        "call_duration_sigma": 1.2,
        "sms_per_day_lambda": 0.5,
        "data_mb_per_day_mu": 20,
        "data_mb_per_day_sigma": 0.5,
        "intl_call_prob": 0.01,
        "fraud_multiplier": 2.0,
        "age_range": (60, 85),
        "professions": ["Retired"],
    },
}

# ─── EVENT TYPES (v1 implementation) 
EVENT_TYPES = {
    # event_key: {name, category, is_chargeable, fraud_risk_level, weight}
    1:  {"name": "Call Initiated",       "category": "Voice",    "is_chargeable": True,  "fraud_risk": "Medium", "weight": 0.30},
    2:  {"name": "SMS Sent",             "category": "Messaging","is_chargeable": True,  "fraud_risk": "Low",    "weight": 0.20},
    3:  {"name": "Data Session Start",   "category": "Data",     "is_chargeable": True,  "fraud_risk": "Low",    "weight": 0.20},
    4:  {"name": "Billing Charge Event", "category": "Billing",  "is_chargeable": True,  "fraud_risk": "High",   "weight": 0.05},
    5:  {"name": "Recharge Event",       "category": "Billing",  "is_chargeable": False, "fraud_risk": "Medium", "weight": 0.05},
    6:  {"name": "Tariff Change",        "category": "Admin",    "is_chargeable": False, "fraud_risk": "Medium", "weight": 0.02},
    7:  {"name": "International Call",   "category": "Voice",    "is_chargeable": True,  "fraud_risk": "High",   "weight": 0.08},
    8:  {"name": "Cell Tower Change",    "category": "Network",  "is_chargeable": False, "fraud_risk": "High",   "weight": 0.03},
    9:  {"name": "SIM Swap Event",       "category": "Security", "is_chargeable": False, "fraud_risk": "Critical","weight": 0.01},
    10: {"name": "Device Registration",  "category": "Security", "is_chargeable": False, "fraud_risk": "High",   "weight": 0.02},
    11: {"name": "Short Call (<5sec)",   "category": "Voice",    "is_chargeable": False, "fraud_risk": "High",   "weight": 0.04},
}

# ─── CHANNELS 
CHANNELS = [
    {"channel_id": 1, "channel_name": "Mobile App",   "channel_type": "Digital"},
    {"channel_id": 2, "channel_name": "USSD",         "channel_type": "Network"},
    {"channel_id": 3, "channel_name": "SMS",          "channel_type": "Network"},
    {"channel_id": 4, "channel_name": "IVR",          "channel_type": "Phone"},
    {"channel_id": 5, "channel_name": "Web Portal",   "channel_type": "Digital"},
    {"channel_id": 6, "channel_name": "Retail Store", "channel_type": "Physical"},
]

# ─── FRAUD SCENARIOS 
FRAUD_SCENARIOS = {
    "SIM Box": {
        "description": "High volume of short calls from one location",
        "events": [1, 11, 11, 11, 8],   # Call + many short calls + tower change
        "score_range": (0.75, 0.99),
        "weight": 0.25,
    },
    "International Fraud": {
        "description": "High international calls with short duration",
        "events": [7, 7, 7, 11, 4],
        "score_range": (0.65, 0.90),
        "weight": 0.25,
    },
    "SIM Swap": {
        "description": "SIM swap followed by account takeover",
        "events": [9, 10, 7, 4],        # SIM swap + device reg + intl call + charge
        "score_range": (0.80, 0.99),
        "weight": 0.20,
    },
    "Premium Rate": {
        "description": "Repeated calls to premium-rate numbers",
        "events": [1, 4, 1, 4, 1, 4],
        "score_range": (0.60, 0.85),
        "weight": 0.15,
    },
    "Roaming Abuse": {
        "description": "Abnormal data usage during roaming",
        "events": [3, 3, 3, 8, 7],
        "score_range": (0.55, 0.80),
        "weight": 0.15,
    },
}

# ─── TEMPORAL PATTERNS 
# Hour weights (0-23): how likely events are per hour
HOUR_WEIGHTS = [
    0.005, 0.003, 0.002, 0.001, 0.001, 0.005,  # 00-05
    0.020, 0.045, 0.065, 0.075, 0.072, 0.070,  # 06-11
    0.068, 0.065, 0.063, 0.060, 0.065, 0.075,  # 12-17
    0.082, 0.078, 0.065, 0.050, 0.030, 0.015,  # 18-23
]

# Day of week weights (0=Monday, 6=Sunday)
DOW_WEIGHTS = [1.0, 1.0, 0.98, 0.97, 1.05, 0.85, 0.75]

# Month seasonality
MONTH_WEIGHTS = [0.95, 0.90, 0.98, 1.00, 1.02, 1.05, 1.10, 1.08, 1.03, 1.00, 0.97, 1.12]
