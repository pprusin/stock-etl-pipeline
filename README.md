# Stock ETL Pipeline — projekt portfolio (Data Engineering)

Pipeline ETL do danych giełdowych, pokazujący pełny przepływ danych "od API do dashboardu"
w oparciu wyłącznie o darmowe warstwy usług (cloud free tier, Databricks Community Edition,
darmowy PostgreSQL).

## Architektura

```
Yahoo Finance (yfinance)
        │
        ▼
  src/extract.py  ──► raw/*.parquet ──► S3 (bronze, raw layer)
        │
        ▼
  Databricks (Delta Lake, medallion architecture)
    ├─ bronze  – surowe dane OHLCV, bez zmian
    ├─ silver  – oczyszczone: braki danych, duplikaty, typy, kalendarz sesji giełdowej
    └─ gold    – agregaty: SMA/EMA, dzienna zmienność %, rolling volatility, korelacje
        │
        ▼
  src/load_to_postgres.py ──► PostgreSQL (warstwa serwująca, free tier: Supabase/Neon)
        │
        ▼
  dashboard/app.py (Streamlit) ──► wizualizacja: ceny, wskaźniki, top gainers/losers
```

Całość odpalana automatycznie raz dziennie przez GitHub Actions (`.github/workflows/daily_pipeline.yml`).

## Stack

| Warstwa          | Narzędzie                          | Koszt              |
|------------------|-------------------------------------|---------------------|
| Źródło danych    | `yfinance` (Python)                | darmowe             |
| Storage raw      | AWS S3 (free tier, 5GB)            | darmowe             |
| Transformacje    | Databricks Community Edition       | darmowe             |
| Warstwa serwująca| PostgreSQL (Supabase / Neon)       | darmowe             |
| Orkiestracja     | GitHub Actions (cron)              | darmowe             |
| Dashboard        | Streamlit Community Cloud          | darmowe             |

## Zakres danych

Domyślnie ~15-20 spółek z S&P500 (łatwo rozszerzalne przez zmienną `TICKERS` w `.env`),
dane dzienne OHLCV (open, high, low, close, volume) z historii ostatnich ~5 lat + codzienny
przyrost. Aktualna konfiguracja lokalna obejmuje też kilka ETF-ów (`SPY`, `QQQ`, `VOO`)
oraz spółki z GPW (`PKO.WA`, `PKN.WA`, `KGH.WA`, `CDR.WA`).

## Ograniczenia

`yfinance` korzysta z nieoficjalnego, niewspieranego API Yahoo Finance (scraping).
Świetne do celów edukacyjnych/portfolio, ale nieodpowiednie do zastosowań produkcyjnych
wymagających gwarancji SLA czy licencjonowanych danych rynkowych.

## Status projektu

- [x] Struktura repo
- [x] `src/extract.py` — pobieranie danych i zapis do Parquet
- [x] Upload do S3
- [ ] Databricks: bronze → silver → gold (Delta Lake)
- [ ] Load do PostgreSQL
- [ ] Dashboard Streamlit
- [ ] Automatyzacja (GitHub Actions)

## Setup lokalny

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Utwórz plik `.env` (ignorowany przez git) z:

```
S3_BUCKET=<nazwa-bucketu-s3>
AWS_ACCESS_KEY_ID=<klucz-iam-usera-z-uprawnieniami-put/list-na-buckecie>
AWS_SECRET_ACCESS_KEY=<sekret>
AWS_DEFAULT_REGION=<region-bucketu>
TICKERS=<lista-tickerow-po-przecinku>   # opcjonalne, domyślnie koszyk z kodu
PERIOD=5y                                # opcjonalne, ale musi mieć wartość — pusty string nadpisuje domyślne "5y"
```

Następnie:

```bash
python src/extract.py
```
