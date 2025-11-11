

####1) Create schema & tables (run in psql)

CREATE SCHEMA IF NOT EXISTS fcfp;

####-- Dimensions
CREATE TABLE fcfp.dim_customer (
  customer_id      TEXT PRIMARY KEY,
  segment          TEXT CHECK (segment IN ('RETAIL','SME','CORP')),
  onboarding_dt    DATE,
  kyc_status       TEXT CHECK (kyc_status IN ('PASSED','REVIEW','FAILED')),
  is_pep           BOOLEAN,
  residence_country TEXT
);

CREATE TABLE fcfp.dim_account (
  account_id    TEXT PRIMARY KEY,
  customer_id   TEXT NOT NULL REFERENCES fcfp.dim_customer(customer_id),
  account_type  TEXT CHECK (account_type IN ('CURRENT','SAVINGS','CREDIT_CARD')),
  opened_dt     DATE,
  status        TEXT CHECK (status IN ('ACTIVE','DORMANT','CLOSED')),
  risk_segment  TEXT CHECK (risk_segment IN ('LOW','MEDIUM','HIGH'))
);

CREATE TABLE fcfp.dim_calendar (
  dt      DATE PRIMARY KEY,
  month   SMALLINT,
  quarter TEXT,
  year    INT
);

####-- Facts
CREATE TABLE fcfp.fact_transactions (
  txn_id       TEXT PRIMARY KEY,
  customer_id  TEXT NOT NULL REFERENCES fcfp.dim_customer(customer_id),
  account_id   TEXT NOT NULL REFERENCES fcfp.dim_account(account_id),
  txn_dt       DATE NOT NULL REFERENCES fcfp.dim_calendar(dt),
  amount       NUMERIC(18,2) NOT NULL,
  currency     TEXT,
  country      TEXT,
  channel      TEXT CHECK (channel IN ('ONLINE','ATM','BRANCH','POS')),
  is_flagged   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE fcfp.fact_alerts (
  alert_id     TEXT PRIMARY KEY,
  customer_id  TEXT NOT NULL REFERENCES fcfp.dim_customer(customer_id),
  alert_dt     DATE NOT NULL REFERENCES fcfp.dim_calendar(dt),
  region       TEXT,
  country      TEXT,
  risk_level   TEXT CHECK (risk_level IN ('LOW','MEDIUM','HIGH')),
  alert_type   TEXT CHECK (alert_type IN ('SANCTIONS','TM_RULE','NAME_SCREEN','PEP_MATCH')),
  txn_count    INT,
  amount       NUMERIC(18,2),
  channel      TEXT CHECK (channel IN ('ONLINE','ATM','BRANCH','POS'))
);

####-- Helpful indexes
CREATE INDEX ON fcfp.fact_transactions (txn_dt);
CREATE INDEX ON fcfp.fact_transactions (customer_id);
CREATE INDEX ON fcfp.fact_alerts (alert_dt);
CREATE INDEX ON fcfp.fact_alerts (customer_id);

#### Populate calendar (pure SQL)
INSERT INTO fcfp.dim_calendar (dt, month, quarter, year)
SELECT d::date,
       EXTRACT(MONTH FROM d)::smallint,
       'Q' || CEIL(EXTRACT(MONTH FROM d)/3.0)::int,
       EXTRACT(YEAR FROM d)::int
FROM generate_series('2024-01-01'::date, '2025-12-31'::date, interval '1 day') AS g(d)
ON CONFLICT (dt) DO NOTHING;


