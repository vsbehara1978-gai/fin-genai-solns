



# make_synth_data.py
# Synthetic FC&FP data generator with purposeful distributions, correlations, and sanity checks.

import random
import numpy as np
import pandas as pd
from faker import Faker
from datetime import date, timedelta
from collections import Counter

# -------------------------
# CONFIG (edit these only)
# -------------------------
N_CUSTOMERS     = 50           # ~50 customers
ACCTS_PER_C     = (4, 4)       # -> ~200 accounts total
N_TRANSACTIONS  = 1000         # fact_transactions rows
N_ALERTS_TARGET = 1000         # fact_alerts target rows (top-up if needed)

START_DT = date(2024, 1, 1)
END_DT   = date(2025, 12, 31)

# category universes
COUNTRIES_EU   = ["NL","DE","FR","BE","IT","ES","PL","CZ","HU","AT","IE"]
CURRENCIES     = ["EUR","USD","GBP"]
CHANNELS       = ["ONLINE","ATM","BRANCH","POS"]
SEGMENTS       = ["RETAIL","SME","CORP"]
KYC_STATUS     = ["PASSED","REVIEW","FAILED"]
ACC_TYPES      = ["CURRENT","SAVINGS","CREDIT_CARD"]
ACC_STATUS     = ["ACTIVE","DORMANT","CLOSED"]
RISK_SEG       = ["LOW","MEDIUM","HIGH"]
RISK_LEVEL     = ["LOW","MEDIUM","HIGH"]
ALERT_TYPES    = ["SANCTIONS","TM_RULE","NAME_SCREEN","PEP_MATCH"]

# weighted distributions
W_SEGMENTS     = [0.82, 0.15, 0.03]
W_KYC_STATUS   = [0.85, 0.12, 0.03]
W_ACC_TYPES    = [0.55, 0.35, 0.10]
W_ACC_STATUS   = [0.90, 0.07, 0.03]
W_ACC_RISKSEG  = [0.70, 0.23, 0.07]
W_CHANNELS     = [0.60, 0.10, 0.15, 0.15]  # ONLINE, ATM, BRANCH, POS
W_ALERT_TYPES  = [0.30, 0.45, 0.20, 0.05]  # SANCTIONS, TM_RULE, NAME_SCREEN, PEP_MATCH

# correlations / knobs
PEP_RATE                 = 0.02
FLAGGED_BASE_RATE        = 0.08    # base flagged txn prob
FLAGGED_BOOST_HIGH_ACC   = 0.06    # +6% for high-risk accounts
FLAGGED_BOOST_Q4         = 0.04    # +4% in Q4
FLAGGED_BOOST_ATM        = 0.02    # +2% for ATM
HIGH_RISK_ALERT_BUMP_AMT = 5000.0  # alerts over this more likely HIGH

# seasonality bias months (more activity)
SEASONAL_MONTHS = [5, 6, 11, 12]
SEASONAL_BIAS_P = 0.25  # 25% of events biased into seasonal months

# amount distribution
LOGN_MEAN = 3.2
LOGN_SIG  = 0.8
SPIKE_P   = 0.01
SPIKE_X   = 20.0
AMOUNT_SCALE = 10.0

# reproducibility
Faker.seed(42)
random.seed(42)
np.random.seed(42)
fake = Faker()

# -------------------------
# helpers
# -------------------------
def rand_date():
    total_days = (END_DT - START_DT).days + 1
    return START_DT + timedelta(days=random.randint(0, total_days - 1))

def seasonal_date():
    """Bias a portion of dates into seasonal months, else uniform."""
    if random.random() < SEASONAL_BIAS_P:
        y = random.choice([2024, 2025])
        m = random.choice(SEASONAL_MONTHS)
        d = random.randint(1, 28)
        return date(y, m, d)
    return rand_date()

def wchoice(items, weights):
    return random.choices(items, weights=weights, k=1)[0]

def quarter_of(dt: date) -> str:
    return f"Q{((dt.month - 1)//3) + 1}"

# -------------------------
# generate DIMs
# -------------------------
customers = []
for i in range(N_CUSTOMERS):
    cid = f"CUST-{i:04d}"
    seg = wchoice(SEGMENTS, W_SEGMENTS)
    onboard = START_DT - timedelta(days=random.randint(30, 3650))
    kyc = wchoice(KYC_STATUS, W_KYC_STATUS)
    pep = random.random() < PEP_RATE
    country = random.choice(COUNTRIES_EU)
    customers.append([cid, seg, onboard, kyc, pep, country])

df_cust = pd.DataFrame(customers, columns=[
    "customer_id","segment","onboarding_dt","kyc_status","is_pep","residence_country"
])

accounts = []
for _, row in df_cust.iterrows():
    n_accts = random.randint(*ACCTS_PER_C)
    for j in range(n_accts):
        aid = f"ACC-{row['customer_id'].split('-')[1]}-{j:02d}"
        atype = wchoice(ACC_TYPES, W_ACC_TYPES)
        opened = row["onboarding_dt"] + timedelta(days=random.randint(0, 365*3))
        status = wchoice(ACC_STATUS, W_ACC_STATUS)
        rseg  = wchoice(RISK_SEG, W_ACC_RISKSEG)
        accounts.append([aid, row["customer_id"], atype, opened, status, rseg])

df_acct = pd.DataFrame(accounts, columns=[
    "account_id","customer_id","account_type","opened_dt","status","risk_segment"
])

# calendar dim (derive later in SQL in PG, but we’ll emit CSV for consistency)
cal_days = pd.date_range(START_DT, END_DT, freq="D").date
df_cal = pd.DataFrame({
    "dt": cal_days,
    "month": [d.month for d in cal_days],
    "quarter": [quarter_of(d) for d in cal_days],
    "year": [d.year for d in cal_days]
})

# -------------------------
# generate FACT: transactions with correlations
# -------------------------
acct_ids = df_acct["account_id"].values
cust_for_acct = dict(zip(df_acct["account_id"], df_acct["customer_id"]))
risk_for_acct = dict(zip(df_acct["account_id"], df_acct["risk_segment"]))
type_for_acct = dict(zip(df_acct["account_id"], df_acct["account_type"]))

txn_rows = []
for i in range(N_TRANSACTIONS):
    aid = random.choice(acct_ids)
    cid = cust_for_acct[aid]
    txn_dt = seasonal_date()
    # amounts with spikes
    base = np.random.lognormal(mean=LOGN_MEAN, sigma=LOGN_SIG)
    if random.random() < SPIKE_P:
        base *= SPIKE_X
    amount = round(base * AMOUNT_SCALE, 2)
    currency = wchoice(CURRENCIES, [0.9, 0.08, 0.02])
    country = random.choice(COUNTRIES_EU)
    channel = wchoice(CHANNELS, W_CHANNELS)

    # flagged probability with boosts
    p_flag = FLAGGED_BASE_RATE
    if risk_for_acct[aid] == "HIGH":
        p_flag += FLAGGED_BOOST_HIGH_ACC
    if quarter_of(txn_dt) == "Q4":
        p_flag += FLAGGED_BOOST_Q4
    if channel == "ATM":
        p_flag += FLAGGED_BOOST_ATM
    is_flagged = (random.random() < p_flag)

    txn_rows.append([f"TXN-{i:06d}", cid, aid, txn_dt, amount, currency, country, channel, is_flagged])

df_txn = pd.DataFrame(txn_rows, columns=[
    "txn_id","customer_id","account_id","txn_dt","amount","currency","country","channel","is_flagged"
])

# -------------------------
# generate FACT: alerts
# - derive from flagged transactions grouped by customer/day/channel
# - ensure coverage across alert types & risk levels
# -------------------------
alerts = []
flagged = df_txn[df_txn["is_flagged"] == True]
grp = flagged.groupby(["customer_id","txn_dt","channel"], sort=False)
seq = 0
for (cid, adt, ch), g in grp:
    total_amt = float(g["amount"].sum())
    txn_count = int(g.shape[0])
    region = "EU"
    country = random.choice(COUNTRIES_EU)
    # risk level: higher amount -> more likely HIGH
    if total_amt >= HIGH_RISK_ALERT_BUMP_AMT:
        rlevel = wchoice(RISK_LEVEL, [0.30, 0.35, 0.35])
    else:
        rlevel = wchoice(RISK_LEVEL, [0.65, 0.28, 0.07])
    # alert type: bias TM_RULE for CREDIT_CARD / ONLINE
    atype_base = list(W_ALERT_TYPES)
    if ch == "ONLINE" or (df_acct.loc[df_acct["account_id"] == g.iloc[0]["account_id"], "account_type"].iloc[0] == "CREDIT_CARD"):
        atype_base = [0.20, 0.60, 0.15, 0.05]
    atype = wchoice(ALERT_TYPES, atype_base)

    alerts.append([f"ALT-{seq:06d}", cid, adt, region, country, rlevel, atype, txn_count, round(total_amt,2), ch])
    seq += 1

# top-up to target with generic sanctions/name_screen/pep_match across customers
while len(alerts) < N_ALERTS_TARGET:
    cid = random.choice(df_cust["customer_id"].values)
    adt = seasonal_date()
    ch  = wchoice(CHANNELS, W_CHANNELS)
    atype = wchoice(ALERT_TYPES, [0.40, 0.20, 0.30, 0.10])  # more sanctions & name screen
    rlevel = wchoice(RISK_LEVEL, [0.60, 0.30, 0.10])
    txn_count = random.randint(1, 4)
    amt = float(np.random.lognormal(LOGN_MEAN, LOGN_SIG) * AMOUNT_SCALE)
    alerts.append([f"ALT-{seq:06d}", cid, adt, "EU", random.choice(COUNTRIES_EU), rlevel, atype, txn_count, round(amt,2), ch])
    seq += 1

df_alert = pd.DataFrame(alerts, columns=[
    "alert_id","customer_id","alert_dt","region","country","risk_level","alert_type","txn_count","amount","channel"
])

# -------------------------
# Coverage guards (light checks; adjust if needed)
# -------------------------
def pct_counts(series):
    c = series.value_counts(normalize=True)
    return (c*100).round(1).astype(str) + "%"

print("\n=== Coverage sanity checks ===")
print("Customers by segment:", pct_counts(df_cust["segment"]).to_dict())
print("Customers by KYC:",    pct_counts(df_cust["kyc_status"]).to_dict())
print("Accounts by risk:",    pct_counts(df_acct["risk_segment"]).to_dict())
print("Txns by channel:",     pct_counts(df_txn["channel"]).to_dict())
print("Alerts by type:",      pct_counts(df_alert["alert_type"]).to_dict())
print("Alerts by risk:",      pct_counts(df_alert["risk_level"]).to_dict())

# Ensure each enum category appears (soft enforcement; warn if missing)
def assert_nonempty(name, series, required_values):
    present = set(series.unique())
    missing = [v for v in required_values if v not in present]
    if missing:
        print(f"[WARN] {name}: missing categories {missing}")

assert_nonempty("CHANNELS in txns", df_txn["channel"], CHANNELS)
assert_nonempty("ALERT_TYPES",      df_alert["alert_type"], ALERT_TYPES)
assert_nonempty("RISK_LEVEL",       df_alert["risk_level"], RISK_LEVEL)
assert_nonempty("ACC_TYPES",        df_acct["account_type"], ACC_TYPES)

# Basic overlap check
overlap = len(set(df_alert["customer_id"]).intersection(set(df_txn["customer_id"]))) / max(1,len(df_cust))
print(f"Customer overlap (alerts ∩ txns) ~ {overlap*100:.1f}%")

# Amount spread
print("Txn amount percentiles:", df_txn["amount"].quantile([0.5,0.9,0.99]).to_dict())

# -------------------------
# Save CSVs
# -------------------------
df_cust.to_csv("dim_customer.csv", index=False)
df_acct.to_csv("dim_account.csv", index=False)
df_txn.to_csv("fact_transactions.csv", index=False)
df_alert.to_csv("fact_alerts.csv", index=False)
df_cal.to_csv("dim_calendar.csv", index=False)

print("\nDone. Files written:")
print("  dim_customer.csv, dim_account.csv, dim_calendar.csv, fact_transactions.csv, fact_alerts.csv")
