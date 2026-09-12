import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

st.set_page_config(page_title="Stock ETL Dashboard", layout="wide")

@st.cache_data(ttl=3600)
def load_indicators() -> pd.DataFrame:
    engine = create_engine(DATABASE_URL)

    df = pd.read_sql_query(
        "SELECT * FROM indicators",
        con=engine,
        parse_dates=["date"],
    )

    return df

df = load_indicators()

st.title("Stock ETL Dashboard")

tickers = sorted(df["ticker"].unique())
selected_tickers = st.sidebar.multiselect("Ticker", tickers, default=tickers[:1])

min_date, max_date = df["date"].min(), df["date"].max()
date_range = st.sidebar.date_input(
    "Zakres dat",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

filtered = df[
    df["ticker"].isin(selected_tickers) &
    (df["date"] >= pd.Timestamp(date_range[0])) &
    (df["date"] <= pd.Timestamp(date_range[1]))
]

st.subheader("Cena i średnie kroczące")

for ticker in selected_tickers:
    ticker_df = filtered[filtered["ticker"] == ticker].sort_values("date")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=ticker_df["date"], y=ticker_df["close"], name="close"))
    fig.add_trace(go.Scatter(x=ticker_df["date"], y=ticker_df["sma_20"], name="SMA 20"))
    fig.add_trace(go.Scatter(x=ticker_df["date"], y=ticker_df["sma_50"], name="SMA 50"))

    fig.update_layout(title=ticker, xaxis_title="Data", yaxis_title="Cena")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Top gainers / losers")

by_date = df[
    (df["date"] >= pd.Timestamp(date_range[0])) &
    (df["date"] <= pd.Timestamp(date_range[1]))
]

latest_date = by_date["date"].max()
latest = by_date[by_date["date"] == latest_date]

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Top gainers**")
    st.dataframe(
        latest.sort_values("daily_return_pct", ascending=False)
        .head(5)[["ticker", "date", "close", "daily_return_pct"]]
    )

with col2:
    st.markdown("**Top losers**")
    st.dataframe(
        latest.sort_values("daily_return_pct", ascending=True)
        .head(5)[["ticker", "date", "close", "daily_return_pct"]]
    )