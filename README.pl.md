# Stock ETL Pipeline

[🇬🇧 English](README.md) | 🇵🇱 Polski

Projekt portfolio z zakresu data engineering: codzienny pipeline ETL do danych
giełdowych, "od API do dashboardu", zbudowany wyłącznie na darmowych warstwach usług
(cloud free tier, Databricks Free Edition, darmowy PostgreSQL).

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

Całość odpalana automatycznie raz dziennie przez GitHub Actions
(`.github/workflows/daily_pipeline.yml`).

## Stack

| Warstwa          | Narzędzie                            | Koszt   |
|------------------|----------------------------------------|---------|
| Źródło danych    | `yfinance` (Python)                    | darmowe |
| Storage raw      | AWS S3 (free tier, 5GB)                | darmowe |
| Transformacje    | Databricks Free Edition (serverless)   | darmowe |
| Warstwa serwująca| PostgreSQL (Supabase / Neon)           | darmowe |
| Orkiestracja     | GitHub Actions (cron)                  | darmowe |
| Dashboard        | Streamlit Community Cloud              | darmowe |

## Zakres danych

Domyślnie ~15-20 spółek z S&P 500 (łatwo rozszerzalne przez zmienną `TICKERS` w `.env`),
dane dzienne OHLCV (open, high, low, close, volume) z historii ostatnich ~5 lat plus
codzienny przyrost.

## Wersja live

🔗 [stock-etl-pipeline.streamlit.app](https://stock-etl-pipeline-dduvkozybgtxk7htncr5kp.streamlit.app/)

### Słowniczek pojęć

- **Close** – cena zamknięcia akcji w danym dniu sesyjnym.
- **SMA 20 / SMA 50** – Simple Moving Average: średnia cena zamknięcia z ostatnich
  20 / 50 dni sesyjnych. Wygładza krótkoterminowe wahania i pokazuje trend; różnica
  między tymi dwiema liniami to popularny sygnał kierunku trendu.
- **Volatility 20** – rolling odchylenie standardowe dziennych stóp zwrotu z ostatnich
  20 dni sesyjnych. Im wyższa wartość, tym większe i bardziej nieregularne wahania
  ceny (większe ryzyko).
- **Daily return (%)** – procentowa zmiana ceny zamknięcia względem poprzedniego dnia
  sesyjnego.
- **Top gainers / losers** – 5 spółek z najwyższą / najniższą dzienną stopą zwrotu (%)
  na najnowszą datę w wybranym zakresie.

## Setup

### 1. Klonowanie i instalacja zależności

```bash
git clone <url-tego-repo>
cd stock-etl-pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Konfiguracja zmiennych środowiskowych

Skopiuj `.env.example` do `.env` i uzupełnij wartości:

```bash
cp .env.example .env
```

| Zmienna                  | Wymagana do               | Uwagi                                               |
|--------------------------|----------------------------|------------------------------------------------------|
| `S3_BUCKET`              | `extract.py`               | nazwa bucketu S3                                     |
| `AWS_ACCESS_KEY_ID`      | `extract.py`, `load_to_postgres.py` | IAM user z uprawnieniami put/get/list na buckecie |
| `AWS_SECRET_ACCESS_KEY`  | `extract.py`, `load_to_postgres.py` |                                                 |
| `AWS_DEFAULT_REGION`     | `extract.py`, `load_to_postgres.py` |                                                 |
| `TICKERS`                | `extract.py`               | opcjonalne, lista po przecinku, domyślnie koszyk z kodu |
| `PERIOD`                 | `extract.py`               | opcjonalne, np. `5y` — nie może być pustym stringiem |
| `DATABASE_URL`           | `load_to_postgres.py`, dashboard | connection string do Postgresa (np. Neon)        |
| `DATABRICKS_HOST/TOKEN/JOB_ID` | tylko GitHub Actions  | używane do zdalnego odpalenia joba w Databricksie    |

### 3. Uruchomienie pipeline'u lokalnie

```bash
python src/extract.py             # pobranie danych -> raw/*.parquet -> upload do S3 (bronze)
# ... uruchom job w Databricksie (patrz niżej), żeby gold/*.parquet trafiło na S3 ...
python src/load_to_postgres.py    # S3 (gold) -> Postgres
streamlit run dashboard/app.py    # dashboard lokalnie
```

### 4. Setup Databricks (bronze → silver → gold)

Workspace: [Databricks Free Edition](https://community.cloud.databricks.com)
(serverless-only — brak możliwości tworzenia własnych klastrów, więc S3 podpięte jest
przez `boto3` + Databricks Secrets, nie przez `fs.s3a` config na klastrze).

```bash
pip install databricks-cli   # albo nowy unified CLI: https://github.com/databricks/cli/releases
databricks configure --token   # host = URL workspace'u, token = User Settings -> Developer -> Access tokens
databricks secrets create-scope stock-etl
databricks secrets put-secret stock-etl aws-access-key-id --string-value "$AWS_ACCESS_KEY_ID"
databricks secrets put-secret stock-etl aws-secret-access-key --string-value "$AWS_SECRET_ACCESS_KEY"
```

Następnie utwórz 5 notebooków w UI Databricksa (nie są częścią tego repo):

- `00_config` — widget `s3_bucket`, odczyt sekretów AWS (`dbutils.secrets.get`), klient
  `boto3`, utworzenie schematów `workspace.bronze` / `workspace.silver` / `workspace.gold`
- `01_bronze` → `02_silver` → `03_gold` → `04_export`, każdy dołącza `%run ./00_config` i
  odpowiada za jedną warstwę medalionu (`04_export` eksportuje gold z powrotem do S3)

**Pułapka #1**: `dbutils.widgets.text(...)` nie nadpisuje wartości już istniejącego
widgetu — zmiana defaultu w kodzie wymaga też ręcznej zmiany wartości w polu widgetu w
notebooku (albo `dbutils.widgets.removeAll()`).

**Pułapka #2**: na serverless compute natywny zapis Sparka do S3
(`df.write.parquet("s3://...")`) kończy się `CloudAccessDeniedException` — Unity Catalog
wymaga zarejestrowanego External Location + Storage Credential dla tej ścieżki, a
`spark.conf.set("spark.hadoop.fs.s3a...")` jest zablokowane (`CONFIG_NOT_AVAILABLE`).
Obejście: zbierz dane przez `.collect()` do pandas i wgraj przez `boto3`/`put_object`
(patrz `04_export`). Pamiętaj też o rozszerzeniu polityki IAM (`s3:PutObject`/`s3:GetObject`)
o prefiks `gold/*` — domyślna polityka z etapu bronze obejmuje tylko `bronze/ohlcv/*`.

### 5. Automatyzacja przez GitHub Actions

Dodaj zmienne z kroku 2 jako sekrety repozytorium (Settings → Secrets and variables →
Actions). Workflow `daily_pipeline.yml` odpala wtedy cały łańcuch raz dziennie
(`extract.py` → trigger joba w Databricksie i oczekiwanie na wynik → `load_to_postgres.py`),
a dodatkowo można go odpalić ręcznie z zakładki Actions.

## Ograniczenia

`yfinance` korzysta z nieoficjalnego, niewspieranego API Yahoo Finance (scraping).
Świetne do celów edukacyjnych/portfolio, ale nieodpowiednie do zastosowań produkcyjnych
wymagających gwarancji SLA czy licencjonowanych danych rynkowych.
