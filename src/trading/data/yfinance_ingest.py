from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from trading.storage.bars import BarsStore

log = logging.getLogger(__name__)

_BARS_COLS = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]


def _normalize(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Coerce a yfinance OHLCV frame into the BarsStore schema.

    Handles both the flat-column shape and the single-ticker MultiIndex shape
    that recent yfinance versions return by default.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=_BARS_COLS)

    df = df.copy()
    # A list/MultiIndex on columns (('Open', 'AAPL'), …) → keep the price field.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.reset_index()
    date_col = next(
        (c for c in ("Date", "Datetime", "index") if c in df.columns), df.columns[0]
    )

    out = pd.DataFrame()
    out["ticker"] = [ticker] * len(df)
    out["date"] = pd.to_datetime(df[date_col]).dt.date
    out["open"] = pd.to_numeric(df.get("Open"), errors="coerce")
    out["high"] = pd.to_numeric(df.get("High"), errors="coerce")
    out["low"] = pd.to_numeric(df.get("Low"), errors="coerce")
    out["close"] = pd.to_numeric(df.get("Close"), errors="coerce")
    # auto_adjust=False yields "Adj Close"; fall back to Close if absent.
    adj = df["Adj Close"] if "Adj Close" in df.columns else df.get("Close")
    out["adj_close"] = pd.to_numeric(adj, errors="coerce")
    out["volume"] = pd.to_numeric(df.get("Volume"), errors="coerce")

    out = out.dropna(subset=["open", "high", "low", "close", "adj_close"])
    out["volume"] = out["volume"].fillna(0).astype("int64")
    return out[_BARS_COLS].reset_index(drop=True)


def ingest_ticker(
    store: BarsStore, ticker: str, history_days: int = 400, full: bool = False
) -> int:
    """Fetch daily bars for one ticker and upsert them. Returns rows written.

    Incremental by default: re-pulls only the last few sessions on top of what
    is already stored (cheap, and catches adj_close revisions). `full=True`, or
    an empty store, fetches the entire `history_days` window. Network/symbol
    errors are swallowed and reported as 0 rows so a single bad ticker never
    aborts a universe run.
    """
    start: str | None = None
    if not full:
        latest = store.latest_date(ticker)
        if latest is not None:
            start = (latest - pd.Timedelta(days=5)).date().isoformat()
    if start is None:
        start = (date.today() - timedelta(days=max(history_days, 1))).isoformat()

    try:
        df = yf.download(
            ticker,
            start=start,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:  # noqa: BLE001 — one ticker failing must not abort the run
        log.warning("download failed for %s: %s", ticker, exc)
        return 0

    norm = _normalize(df, ticker)
    if norm.empty:
        log.warning("no bars returned for %s", ticker)
        return 0
    return store.upsert(norm)


def ingest_universe(
    store: BarsStore,
    tickers: list[str],
    history_days: int = 400,
    full: bool = False,
) -> dict[str, int]:
    """Ingest each ticker in `tickers`. Returns {ticker: rows_written}."""
    counts: dict[str, int] = {}
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        n = ingest_ticker(store, ticker, history_days=history_days, full=full)
        counts[ticker] = n
        log.info("[%d/%d] %s: %d rows", i, total, ticker, n)
    return counts
