# Stock ETL Pipeline

🇬🇧 English | [🇵🇱 Polski](README.pl.md)

A portfolio data engineering project: a daily ETL pipeline for stock market data,
"from API to dashboard", built entirely on free-tier services (cloud free tier,
Databricks Free Edition, free PostgreSQL).

## Architecture

```
Yahoo Finance (yfinance)
        │
        ▼
  src/extract.py  ──► raw/*.parquet ──► S3 (bronze, raw layer)
        │
        ▼
  Databricks (Delta Lake, medallion architecture, Unity Catalog: workspace.<schema>.<table>)
    ├─ bronze  – raw OHLCV data, unchanged
    ├─ silver  – cleaned: missing data, duplicates, types, exchange trading calendar
    └─ gold    – aggregates: SMA/EMA, daily % change, rolling volatility, correlations
        │
        ▼
  src/load_to_postgres.py ──► PostgreSQL (serving layer, free tier: Supabase/Neon)
        │
        ▼
  dashboard/app.py (Streamlit) ──► visualization: prices, indicators, top gainers/losers
```

The whole pipeline runs automatically once a day via GitHub Actions
(`.github/workflows/daily_pipeline.yml`).

## Stack

| Layer          | Tool                                  | Cost  |
|----------------|----------------------------------------|-------|
| Data source    | `yfinance` (Python)                    | free  |
| Raw storage    | AWS S3 (free tier, 5GB)                | free  |
| Transformations| Databricks Free Edition (serverless)   | free  |
| Serving layer  | PostgreSQL (Supabase / Neon)           | free  |
| Orchestration  | GitHub Actions (cron)                  | free  |
| Dashboard      | Streamlit Community Cloud              | free  |

## Data scope

By default ~15-20 S&P 500 companies (easily extendable via the `TICKERS` variable in
`.env`), daily OHLCV data (open, high, low, close, volume) covering the last ~5 years
plus a daily incremental update.

## Live demo

🔗 [stock-etl-pipeline.streamlit.app](https://stock-etl-pipeline-dduvkozybgtxk7htncr5kp.streamlit.app/)

### Glossary

- **Close** – the closing price of the stock on a given trading day.
- **SMA 20 / SMA 50** – Simple Moving Average: the average closing price over the last
  20 / 50 trading days. Smooths out short-term noise to show the underlying trend; the
  gap between the two is a common trend-direction signal.
- **Volatility 20** – rolling standard deviation of daily returns over the last 20
  trading days. Higher values mean bigger, more erratic price swings (more risk).
- **Daily return (%)** – the percentage change in closing price versus the previous
  trading day.
- **Top gainers / losers** – the 5 tickers with the highest / lowest daily return (%)
  on the most recent date in the selected range.

## Setup

### 1. Clone and install dependencies

```bash
git clone <this-repo-url>
cd stock-etl-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in the values:

```bash
cp .env.example .env
```

| Variable                | Required for              | Notes                                              |
|--------------------------|---------------------------|-----------------------------------------------------|
| `S3_BUCKET`              | `extract.py`               | S3 bucket name                                      |
| `AWS_ACCESS_KEY_ID`      | `extract.py`, `load_to_postgres.py` | IAM user with put/get/list on the bucket   |
| `AWS_SECRET_ACCESS_KEY`  | `extract.py`, `load_to_postgres.py` |                                              |
| `AWS_DEFAULT_REGION`     | `extract.py`, `load_to_postgres.py` |                                              |
| `TICKERS`                | `extract.py`               | optional, comma-separated, defaults to code basket |
| `PERIOD`                 | `extract.py`               | optional, e.g. `5y` — must not be an empty string  |
| `DATABASE_URL`           | `load_to_postgres.py`, dashboard | Postgres connection string (e.g. Neon)        |
| `DATABRICKS_HOST/TOKEN/JOB_ID` | GitHub Actions only  | used to trigger the Databricks job remotely        |

### 3. Run the pipeline locally

```bash
python src/extract.py             # fetch data -> raw/*.parquet -> upload to S3 (bronze)
# ... run the Databricks job (see below) so gold/*.parquet lands on S3 ...
python src/load_to_postgres.py    # S3 (gold) -> Postgres
streamlit run dashboard/app.py    # local dashboard
```

### 4. Set up Databricks (bronze → silver → gold)

Workspace: [Databricks Free Edition](https://community.cloud.databricks.com)
(serverless-only — no custom clusters, so S3 access goes through `boto3` + Databricks
Secrets rather than a cluster-level `fs.s3a` config).

```bash
pip install databricks-cli   # or the new unified CLI: https://github.com/databricks/cli/releases
databricks configure --token   # host = workspace URL, token = User Settings -> Developer -> Access tokens
databricks secrets create-scope stock-etl
databricks secrets put-secret stock-etl aws-access-key-id --string-value "$AWS_ACCESS_KEY_ID"
databricks secrets put-secret stock-etl aws-secret-access-key --string-value "$AWS_SECRET_ACCESS_KEY"
```

Then create 5 notebooks in the Databricks UI (not part of this repo):

- `00_config` — `s3_bucket` widget, reads AWS secrets (`dbutils.secrets.get`), a `boto3`
  client, creates the `workspace.bronze` / `workspace.silver` / `workspace.gold` schemas
- `01_bronze` → `02_silver` → `03_gold` → `04_export`, each `%run ./00_config` and each
  responsible for one medallion layer (`04_export` writes the gold layer back to S3)

**Gotcha #1**: `dbutils.widgets.text(...)` doesn't overwrite an existing widget's value —
changing a default in code also requires updating the value in the notebook's widget field
(or calling `dbutils.widgets.removeAll()`).

**Gotcha #2**: on serverless compute, a native Spark write to S3
(`df.write.parquet("s3://...")`) fails with `CloudAccessDeniedException` — Unity Catalog
requires a registered External Location + Storage Credential for that path, and
`spark.conf.set("spark.hadoop.fs.s3a...")` is blocked (`CONFIG_NOT_AVAILABLE`). Workaround:
`.collect()` into pandas and upload via `boto3`/`put_object` (see `04_export`). Also remember
to extend the IAM policy (`s3:PutObject`/`s3:GetObject`) to the `gold/*` prefix — the bronze
policy only covers `bronze/ohlcv/*`.

### 5. Automate with GitHub Actions

Add the variables from step 2 as repository secrets (Settings → Secrets and variables →
Actions). The `daily_pipeline.yml` workflow then runs the full chain once a day
(`extract.py` → trigger the Databricks job and wait for it → `load_to_postgres.py`), and
can also be triggered manually from the Actions tab.

## Limitations

`yfinance` relies on Yahoo Finance's unofficial, unsupported API (scraping). Great for
educational/portfolio purposes, but not suitable for production use cases that need SLA
guarantees or licensed market data.
