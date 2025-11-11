
#### Load CSVs into Postgres (fast path: COPY)

\copy fcfp.dim_customer     FROM 'dim_customer.csv'     CSV HEADER;
\copy fcfp.dim_account      FROM 'dim_account.csv'      CSV HEADER;
\copy fcfp.fact_transactions FROM 'fact_transactions.csv' CSV HEADER;
\copy fcfp.fact_alerts      FROM 'fact_alerts.csv'      CSV HEADER;

### Before loading, first disable the indexes, load the data and then enable the indexes 


#### Validation 

-- Row counts
SELECT 'customers' tbl, COUNT(*) FROM fcfp.dim_customer
UNION ALL SELECT 'accounts', COUNT(*) FROM fcfp.dim_account
UNION ALL SELECT 'txns', COUNT(*) FROM fcfp.fact_transactions
UNION ALL SELECT 'alerts', COUNT(*) FROM fcfp.fact_alerts;

-- Referential integrity spot check
SELECT COUNT(*) invalid_accounts
FROM fcfp.fact_transactions t
LEFT JOIN fcfp.dim_account a ON a.account_id = t.account_id
WHERE a.account_id IS NULL;

-- Basic analytics sanity
SELECT channel, COUNT(*) txns, AVG(amount)::numeric(12,2) avg_amt
FROM fcfp.fact_transactions
GROUP BY channel ORDER BY txns DESC;

-- Alerts over time
SELECT date_trunc('month', alert_dt)::date AS month, alert_type, COUNT(*) cnt
FROM fcfp.fact_alerts
GROUP BY 1,2 ORDER BY 1,2;
