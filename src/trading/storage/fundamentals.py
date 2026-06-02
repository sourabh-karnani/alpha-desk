from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker VARCHAR PRIMARY KEY,
    short_name VARCHAR,
    sector VARCHAR,
    industry VARCHAR,
    market_cap DOUBLE,
    forward_pe DOUBLE,
    trailing_pe DOUBLE,
    trailing_eps DOUBLE,
    forward_eps DOUBLE,
    price_to_book DOUBLE,
    price_to_sales DOUBLE,
    profit_margin DOUBLE,
    roe DOUBLE,
    debt_to_equity DOUBLE,
    revenue_growth DOUBLE,
    earnings_growth DOUBLE,
    analyst_target DOUBLE,
    analyst_recommendation VARCHAR,
    num_analysts INTEGER,
    beta DOUBLE,
    fifty_two_week_high DOUBLE,
    fifty_two_week_low DOUBLE,
    dividend_yield DOUBLE,
    fetched_at TIMESTAMP
);
"""

COLS = [
    "ticker", "short_name", "sector", "industry", "market_cap", "forward_pe",
    "trailing_pe", "trailing_eps", "forward_eps", "price_to_book", "price_to_sales",
    "profit_margin", "roe", "debt_to_equity", "revenue_growth", "earnings_growth",
    "analyst_target", "analyst_recommendation", "num_analysts", "beta",
    "fifty_two_week_high", "fifty_two_week_low", "dividend_yield", "fetched_at",
]


class FundamentalsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.path))
        self._conn.execute(SCHEMA)
        # Migration: ensure short_name column exists on pre-existing DBs
        try:
            self._conn.execute("ALTER TABLE fundamentals ADD COLUMN short_name VARCHAR")
        except Exception:
            pass

    def upsert(self, ticker: str, fundamentals: dict) -> None:
        row = {**fundamentals, "ticker": ticker, "fetched_at": datetime.utcnow()}
        values = [row.get(c) for c in COLS]
        placeholders = ",".join(["?"] * len(COLS))
        self._conn.execute(
            f"INSERT OR REPLACE INTO fundamentals ({','.join(COLS)}) VALUES ({placeholders})",
            values,
        )

    def get(self, ticker: str) -> dict | None:
        df = self._conn.execute(
            "SELECT * FROM fundamentals WHERE ticker = ?", [ticker]
        ).df()
        if df.empty:
            return None
        return df.iloc[0].to_dict()

    def is_stale(self, ticker: str, max_age_days: int = 7) -> bool:
        row = self._conn.execute(
            "SELECT fetched_at FROM fundamentals WHERE ticker = ?", [ticker]
        ).fetchone()
        if row is None or row[0] is None:
            return True
        age = datetime.utcnow() - row[0]
        return age > timedelta(days=max_age_days)

    def load_all(self) -> pd.DataFrame:
        return self._conn.execute("SELECT * FROM fundamentals").df()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> FundamentalsStore:
        return self

    def __exit__(self, *_) -> None:
        self.close()
