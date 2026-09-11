"""
Laduje dane do bazy postgresql "neon_db" do chmury postgres neon.tech
"""

import os
import pandas as pd
import boto3
import io

from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

S3_BUCKET = os.getenv("S3_BUCKET")
DATABASE_URL = os.getenv("DATABASE_URL")

GOLD_TABLES = {
    "gold/indicators/indicators.parquet": "indicators",
    "gold/correlations/correlations.parquet": "correlations",
}

client = boto3.client("s3")

def read_parquet_from_s3(key: str) -> pd.DataFrame:
    response = client.get_object(Bucket=S3_BUCKET, Key=key)
    return pd.read_parquet(io.BytesIO(response["Body"].read()))

def load_to_postgres(df: pd.DataFrame, table_name: str, engine) -> None:
    df.to_sql(table_name, engine, if_exists="replace", index=False)
    print(f"Wgrano {len(df)} wierszy do tabeli '{table_name}'")

def main() -> None:
    engine = create_engine(DATABASE_URL)

    for key, table_name in GOLD_TABLES.items():
        df = read_parquet_from_s3(key)
        load_to_postgres(df, table_name, engine)

if __name__ == "__main__":
    main()