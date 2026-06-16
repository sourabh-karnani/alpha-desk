"""NSE daily-bar ingestion via jugaad-data (an alternative to yfinance).

yfinance is convenient and cross-market, but its NSE coverage can be patchy and
its adjusted closes occasionally drift. jugaad-data pulls directly from NSE's
bhavcopy/quote endpoints and is often cleaner for Indian equities, so it's
offered as a selectable source (`trading ingest --source jugaad`).

NSE has no split/dividend-adjusted close, so `adj_close` is set equal to
`close` here; momentum/SMA signals use `adj_close`, so prefer yfinance for long
historical adjustments or accept the unadjusted series for recent windows.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from trading.storage.bars import BarsStore

log = logging.getLogger(__name__)

_BARS_COLS = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]


def nse_symbol(ticker: str) -> str:
    """'SBIN.NS' -> 'SBIN'; pass through bare NSE symbols unchanged."""
    return ticker.split(".")[0]


def _require_jugaad():
    try:
        from jugaad_data.nse import stock_df  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - only without the dep
        raise RuntimeError(
            "jugaad-data is not installed. It ships in core deps; run `uv sync`."
        ) from exc
    return stock_df


def _normalize(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Coerce a jugaad stock_df frame into the BarsStore schema (tolerant of
    column-name casing differences across jugaad versions)."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=_BARS_COLS)

    cols = {c.lower().strip(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return df[cols[n]]
        return None

    out = pd.DataFrame()
    out["ticker"] = [ticker] * len(df)
    out["date"] = pd.to_datetime(pick("date")).dt.date
    out["open"] = pd.to_numeric(pick("open"), errors="coerce")
    out["high"] = pd.to_numeric(pick("high"), errors="coerce")
    out["low"] = pd.to_numeric(pick("low"), errors="coerce")
    close = pick("close", "ltp")
    out["close"] = pd.to_numeric(close, errors="coerce")
    out["adj_close"] = out["close"]  # NSE provides no adjusted close
    out["volume"] = pd.to_numeric(pick("volume", "tottrdqty"), errors="coerce")

    out = out.dropna(subset=["open", "high", "low", "close"])
    out["volume"] = out["volume"].fillna(0).astype("int64")
    return out[_BARS_COLS].reset_index(drop=True)


def ingest_ticker(
    store: BarsStore, ticker: str, history_days: int = 400, full: bool = False
) -> int:
    """Fetch NSE daily bars for one ticker via jugaad-data and upsert them.

    Incremental by default (mirrors the yfinance ingester). Errors are swallowed
    and reported as 0 rows so one bad symbol never aborts a universe run.
    """
    stock_df = _require_jugaad()

    start: date | None = None
    if not full:
        latest = store.latest_date(ticker)
        if latest is not None:
            start = (latest - pd.Timedelta(days=5)).date()
    if start is None:
        start = date.today() - timedelta(days=max(history_days, 1))

    try:
        df = stock_df(symbol=nse_symbol(ticker), from_date=start, to_date=date.today(),
                      series="EQ")
    except Exception as exc:  # noqa: BLE001 — one ticker failing must not abort the run
        log.warning("jugaad download failed for %s: %s", ticker, exc)
        return 0

    norm = _normalize(df, ticker)
    if norm.empty:
        log.warning("no NSE bars returned for %s", ticker)
        return 0
    return store.upsert(norm)


def ingest_universe(
    store: BarsStore, tickers: list[str], history_days: int = 400, full: bool = False
) -> dict[str, int]:
    counts: dict[str, int] = {}
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        n = ingest_ticker(store, ticker, history_days=history_days, full=full)
        counts[ticker] = n
        log.info("[%d/%d] %s: %d rows (jugaad)", i, total, ticker, n)
    return counts
