from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    ticker VARCHAR NOT NULL,
    date DATE NOT NULL,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    adj_close DOUBLE,
    volume BIGINT,
    PRIMARY KEY (ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_bars_date ON bars(date);
"""

UPSERT_SQL = """
INSERT INTO bars
SELECT ticker, date, open, high, low, close, adj_close, volume FROM incoming
ON CONFLICT (ticker, date) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    adj_close = excluded.adj_close,
    volume = excluded.volume
"""


class BarsStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.path))
        self._conn.execute(SCHEMA)

    def upsert(self, df: pd.DataFrame) -> int:
        if df.empty:
            return 0
        cols = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]
        df = df[cols]
        self._conn.register("incoming", df)
        try:
            self._conn.execute(UPSERT_SQL)
        finally:
            self._conn.unregister("incoming")
        return len(df)

    def load(self, ticker: str | None = None, start=None, end=None) -> pd.DataFrame:
        sql = "SELECT * FROM bars WHERE 1=1"
        params: list = []
        if ticker:
            sql += " AND ticker = ?"
            params.append(ticker)
        if start:
            sql += " AND date >= ?"
            params.append(start)
        if end:
            sql += " AND date <= ?"
            params.append(end)
        sql += " ORDER BY ticker, date"
        return self._conn.execute(sql, params).df()

    def latest_date(self, ticker: str) -> pd.Timestamp | None:
        row = self._conn.execute(
            "SELECT MAX(date) FROM bars WHERE ticker = ?", [ticker]
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return pd.Timestamp(row[0])

    def earliest_date(self, ticker: str) -> pd.Timestamp | None:
        row = self._conn.execute(
            "SELECT MIN(date) FROM bars WHERE ticker = ?", [ticker]
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return pd.Timestamp(row[0])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> BarsStore:
        return self

    def __exit__(self, *_) -> None:
        self.close()
