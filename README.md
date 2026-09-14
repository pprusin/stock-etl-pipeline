# Stock ETL Pipeline — projekt portfolio (Data Engineering)

Pipeline ETL do danych giełdowych, pokazujący pełny przepływ danych "od API do dashboardu"
w oparciu wyłącznie o darmowe warstwy usług (cloud free tier, Databricks Free Edition,
darmowy PostgreSQL).

## Architektura

```
Yahoo Finance (yfinance)
        │
        ▼
  src/extract.py  ──► raw/*.parquet ──► S3 (bronze, raw layer)
        │
        ▼
  Databricks (Delta Lake, medallion architecture, Unity Catalog: workspace.<schema>.<table>)
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
| Transformacje    | Databricks Free Edition (serverless)| darmowe             |
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
- [x] Databricks: bronze → silver → gold (Delta Lake) — patrz sekcja "Setup Databricks" niżej
  - [x] Workspace, CLI, secret scope + klucze AWS, dostęp do S3 zweryfikowany
  - [x] `00_config` — bucket (widget), sekrety, klient `boto3`, schematy `workspace.bronze/silver/gold`
  - [x] `01_bronze` — ingest najnowszego parquet z S3 do `workspace.bronze.ohlcv` (zweryfikowano: 22 tickery × 1290 wierszy = 28380 wierszy)
  - [x] `02_silver` — czyszczenie i dedup (dedup po ticker+date, cast typów, odrzucono 790 wierszy bez sesji handlowej danej giełdy; zweryfikowano: 27590 wierszy)
  - [x] `03_gold` — SMA/EMA (20/50), dzienna zmiana %, rolling volatility (`workspace.gold.indicators`, 27590 wierszy) + macierz korelacji (`workspace.gold.correlations`, 484 pary = 22×22 tickerów)
  - [x] `04_export` — eksport `workspace.gold.indicators` i `workspace.gold.correlations` do S3 jako parquet (`gold/indicators/indicators.parquet`, `gold/correlations/correlations.parquet`), przez `boto3`/`put_object` (natywny zapis Sparka do S3 zablokowany na serverless — brak `fs.s3a` i External Location w Unity Catalog)
- [x] Load do PostgreSQL — `src/load_to_postgres.py`, odczyt parquet z S3 (`boto3`/`get_object`) → `pandas` → `to_sql` do Neon (tabele `indicators`, `correlations`)
- [ ] Dashboard Streamlit — `dashboard/app.py`, dane z Neona (tabela `indicators`, cache'owane przez `st.cache_data`)
  - [x] Połączenie z Postgresem + wczytanie `indicators`
  - [x] Sidebar: wybór tickerów (multiselect) i zakresu dat
  - [x] Wykres ceny (`close`) z SMA 20/50 dla wybranych tickerów (Plotly)
  - [x] Top gainers / losers wg `daily_return_pct` (po wszystkich tickerach, w ramach wybranego zakresu dat)
  - [x] Rolling volatility (`volatility_20`)
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
AWS_ACCESS_KEY_ID=<klucz-iam-usera-z-uprawnieniami-put/get/list-na-buckecie>
AWS_SECRET_ACCESS_KEY=<sekret>
AWS_DEFAULT_REGION=<region-bucketu>
TICKERS=<lista-tickerow-po-przecinku>   # opcjonalne, domyślnie koszyk z kodu
PERIOD=5y                                # opcjonalne, ale musi mieć wartość — pusty string nadpisuje domyślne "5y"
DATABASE_URL=<connection-string-do-postgresa>   # np. z Neon, wymagane tylko dla load_to_postgres.py
```

Następnie:

```bash
python src/extract.py
python src/load_to_postgres.py   # wymaga, żeby 04_export w Databricksie wcześniej wgrał gold/*.parquet na S3
```

## Setup Databricks

Workspace: [Databricks Free Edition](https://community.cloud.databricks.com) (serverless-only —
brak możliwości tworzenia własnych klastrów, więc S3 podpięte jest przez `boto3` + Databricks
Secrets, nie przez `fs.s3a` config na klastrze).

Lokalnie (w `.venv` tego repo):

```bash
pip install databricks-cli   # albo nowy unified CLI: zob. https://github.com/databricks/cli/releases
databricks configure --token  # host = URL workspace'u, token = User Settings → Developer → Access tokens
databricks secrets create-scope stock-etl
databricks secrets put-secret stock-etl aws-access-key-id --string-value "$AWS_ACCESS_KEY_ID"
databricks secrets put-secret stock-etl aws-secret-access-key --string-value "$AWS_SECRET_ACCESS_KEY"
```

Notebooki (tworzone ręcznie w UI Databricksa, na razie nie w tym repo — patrz status wyżej):

- `00_config` — widget `s3_bucket`, odczyt sekretów AWS (`dbutils.secrets.get`), klient `boto3`,
  utworzenie schematów `workspace.bronze` / `workspace.silver` / `workspace.gold` (Unity Catalog,
  domyślny katalog to `workspace`)
- `01_bronze`, `02_silver`, `03_gold`, `04_export` — dołączają `00_config` przez `%run ./00_config`,
  każdy odpowiada za jedną warstwę medalionu (`04_export` eksportuje gold do S3)

Częsta pułapka: `dbutils.widgets.text(...)` nie nadpisuje wartości już istniejącego widgetu —
zmiana defaultu w kodzie wymaga też ręcznej zmiany wartości w polu na górze notebooka (albo
`dbutils.widgets.removeAll()`).

Druga pułapka: na serverless compute (brak własnych klastrów) natywny zapis Sparka do S3
(`df.write.parquet("s3://...")` / `.save(...)`) kończy się `CloudAccessDeniedException` —
Unity Catalog wymaga zarejestrowanego External Location + Storage Credential dla tej ścieżki,
a ustawienie `spark.conf.set("spark.hadoop.fs.s3a...")` jest zablokowane
(`CONFIG_NOT_AVAILABLE`). Obejście: zbierz dane przez `.collect()` do pandas i wgraj przez
`boto3`/`put_object` (tak jak `00_config` robi to już dla odczytu) — patrz `04_export`.
Pamiętaj też o rozszerzeniu polityki IAM (`s3:PutObject`/`s3:GetObject`) o prefiks `gold/*`,
bo domyślna polityka z etapu bronze obejmuje tylko `bronze/ohlcv/*`.
