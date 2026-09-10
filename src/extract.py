"""Pobiera dzienne dane OHLCV dla wskazanych spółek i zapisuje jako Parquet.

Uruchomienie:
    python src/extract.py

Zmienne środowiskowe (opcjonalne, w .env):
    TICKERS      - lista tickerów rozdzielona przecinkami (domyślnie: przykładowy koszyk S&P500)
    PERIOD       - okres historii do pobrania, np. "5y", "1mo" (domyślnie "5y")
    S3_BUCKET    - jeśli ustawione, plik zostanie dodatkowo wysłany do S3 (bronze layer)
"""

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

DEFAULT_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "JPM", "V", "JNJ",
    "WMT", "PG", "MA", "HD", "DIS",
]

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"


def get_tickers() -> list[str]:
    raw = os.getenv("TICKERS")
    if raw:
        return [t.strip().upper() for t in raw.split(",") if t.strip()]
    return DEFAULT_TICKERS


def fetch_ohlcv(tickers: list[str], period: str) -> pd.DataFrame:
    data = yf.download(
        tickers,
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
    )

    frames = []
    for ticker in tickers:
        df = data[ticker].copy()
        df["ticker"] = ticker
        df = df.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        frames.append(df[["date", "ticker", "open", "high", "low", "close", "volume"]])

    return pd.concat(frames, ignore_index=True)


def save_local(df: pd.DataFrame) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RAW_DIR / f"ohlcv_{ts}.parquet"
    df.to_parquet(out_path, index=False)
    return out_path


def upload_to_s3(path: Path) -> None:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        return

    import boto3

    key = f"bronze/ohlcv/{path.name}"
    boto3.client("s3").upload_file(str(path), bucket, key)
    print(f"Wgrano do s3://{bucket}/{key}")


def main() -> None:
    tickers = get_tickers()
    period = os.getenv("PERIOD", "5y")

    print(f"Pobieranie danych dla {len(tickers)} spółek, okres={period}...")
    df = fetch_ohlcv(tickers, period)
    print(f"Pobrano {len(df)} wierszy.")

    out_path = save_local(df)
    print(f"Zapisano lokalnie: {out_path}")

    upload_to_s3(out_path)


if __name__ == "__main__":
    main()
