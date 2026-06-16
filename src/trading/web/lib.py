"""Shared helpers for the Streamlit dashboard: cached data access, config from
session state, and DataFrame shaping for display."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from trading.config.settings import (
    BARS_DUCKDB_PATH,
    DATA_DIR,
    FUNDAMENTALS_DUCKDB_PATH,
    LOGS_DIR,
    STATE_SQLITE_PATH,
    RiskConfig,
)
from trading.config.universe import get_universe, load_snapshot
from trading.storage.bars import BarsStore

UNIVERSES = ["nifty50", "nifty_next_50", "nifty100", "sp100"]
UNIVERSES_DIR = DATA_DIR / "universes"

# ---- config from session state -----------------------------------------

_DEFAULTS = {
    "universe": "nifty50",
    "snapshot_path": "",
    "capital": 100_000.0,
    "max_positions": 10,
    "atr_mult": 2.0,
    "rr": 2.0,
    "sizing_mode": "equal_weight",
    "risk_per_trade_pct": 0.01,
    "max_risk_pct": 0.02,
    "max_position_pct": 0.20,
}


def init_state() -> None:
    for k, v in _DEFAULTS.items():
        st.session_state.setdefault(k, v)


def risk_config() -> RiskConfig:
    ss = st.session_state
    return RiskConfig(
        capital_inr=float(ss["capital"]),
        max_positions=int(ss["max_positions"]),
        atr_stop_multiple=float(ss["atr_mult"]),
        reward_risk_ratio=float(ss["rr"]),
        sizing_mode=ss["sizing_mode"],
        risk_per_trade_pct=float(ss["risk_per_trade_pct"]),
        max_risk_per_trade_pct=float(ss["max_risk_pct"]),
        max_position_pct=float(ss["max_position_pct"]),
    )


def current_tickers() -> list[str]:
    ss = st.session_state
    snap = ss.get("snapshot_path")
    if snap:
        return load_snapshot(Path(snap))
    return get_universe(ss.get("universe", "nifty50"))


def universe_label() -> str:
    snap = st.session_state.get("snapshot_path")
    if snap:
        return f"snapshot:{Path(snap).name}"
    return st.session_state.get("universe", "nifty50")


# ---- cached data access -------------------------------------------------


@st.cache_data(show_spinner=False)
def _load_all_bars(path_str: str, mtime: float) -> pd.DataFrame:
    p = Path(path_str)
    if not p.exists():
        return pd.DataFrame()
    with BarsStore(p) as store:
        return store.load()


def load_bars(tickers: list[str] | None = None) -> pd.DataFrame:
    """Load bars from the DuckDB store (cached by file mtime), filtered to
    `tickers` when given."""
    mtime = BARS_DUCKDB_PATH.stat().st_mtime if BARS_DUCKDB_PATH.exists() else 0.0
    df = _load_all_bars(str(BARS_DUCKDB_PATH), mtime)
    if df.empty or not tickers:
        return df
    return df[df["ticker"].isin(tickers)]


def data_status() -> dict:
    df = load_bars()
    if df.empty:
        return {"tickers": 0, "rows": 0, "start": None, "end": None}
    return {
        "tickers": int(df["ticker"].nunique()),
        "rows": int(len(df)),
        "start": pd.to_datetime(df["date"]).min().date(),
        "end": pd.to_datetime(df["date"]).max().date(),
    }


def fundamentals_count() -> int:
    if not FUNDAMENTALS_DUCKDB_PATH.exists():
        return 0
    try:
        from trading.storage.fundamentals import FundamentalsStore

        with FundamentalsStore(FUNDAMENTALS_DUCKDB_PATH) as fs:
            return int(len(fs.load_all()))
    except Exception:
        return 0


def recent_metrics(limit: int = 15) -> pd.DataFrame:
    from trading.monitoring import read_events

    df = read_events(LOGS_DIR)
    return df.tail(limit).iloc[::-1] if not df.empty else df


# ---- display shaping ----------------------------------------------------

STARS = {i: "★" * i + "☆" * (5 - i) for i in range(1, 6)}


def recs_to_df(recs: list) -> pd.DataFrame:
    rows = []
    for i, r in enumerate(recs, 1):
        rows.append(
            {
                "#": i,
                "Ticker": r.ticker,
                "Dir": r.direction,
                "Entry": round(r.entry, 2),
                "Stop": round(r.stop, 2),
                "Target": round(r.target, 2),
                "Shares": r.shares,
                "Notional ₹": round(r.notional, 0),
                "Risk ₹": round(r.risk_inr, 0),
                "Conv": STARS.get(r.conviction, ""),
                "Score %": round(r.score * 100, 1),
            }
        )
    return pd.DataFrame(rows)


def has_state_db() -> bool:
    return STATE_SQLITE_PATH.exists()
