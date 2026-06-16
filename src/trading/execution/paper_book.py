"""Paper-book simulator.

`open_recommendations` records ideas and opens paper positions (filled by a
`Broker`). `update_positions` walks each open position forward through stored
bars and closes it the first day a stop, target, or time-stop triggers — exactly
the bookkeeping the README promised ("a paper-book scores how recommendations
would have performed"). All state lives in the SQLite `StateStore`, so the book
persists across CLI runs.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading.brokers.base import Broker, Order
from trading.storage.state import StateStore, _signed_pnl

# Recommendation.direction → (open side, close side)
_SIDES = {"LONG": ("buy", "sell"), "SHORT": ("short", "cover")}


def _ts(x) -> pd.Timestamp:
    return pd.Timestamp(x)


def open_recommendations(
    state: StateStore,
    broker: Broker,
    recs: list,
    strategy: str,
) -> list[int]:
    """Persist `recs` and open a paper position for each (filled at its entry).

    Returns the opened position ids. Idempotency is the caller's concern — this
    always opens fresh positions.
    """
    rec_ids = state.record_recommendations(recs, strategy)
    pos_ids: list[int] = []
    for rec, rec_id in zip(recs, rec_ids, strict=True):
        if rec.shares <= 0:
            continue
        open_side, _ = _SIDES[rec.direction.upper()]
        entry_date = _ts(rec.as_of).date().isoformat()
        fill = broker.place(
            Order(rec.ticker, open_side, rec.shares, rec.entry, ts=entry_date)
        )
        pos_id = state.open_position(
            ticker=rec.ticker,
            direction=rec.direction,
            qty=rec.shares,
            entry_price=fill.price,
            entry_date=entry_date,
            stop=rec.stop,
            target=rec.target,
            rec_id=rec_id,
            fee=fill.fee,
        )
        pos_ids.append(pos_id)
    return pos_ids


def _exit_for_day(direction: str, row, stop: float, target: float):
    """Return (exit_price, reason) if this bar triggers an exit, else None.

    Conservative: if both stop and target are touched the same day, assume the
    stop filled first.
    """
    high, low = float(row["high"]), float(row["low"])
    if direction.upper() == "SHORT":
        if stop is not None and high >= stop:
            return stop, "stop"
        if target is not None and low <= target:
            return target, "target"
    else:
        if stop is not None and low <= stop:
            return stop, "stop"
        if target is not None and high >= target:
            return target, "target"
    return None


def update_positions(
    state: StateStore,
    broker: Broker,
    bars: pd.DataFrame,
    max_holding_days: int = 60,
) -> dict[str, int]:
    """Close open positions that hit stop/target/time on bars after their entry.

    Returns a count of closes by reason.
    """
    open_pos = state.get_positions("open")
    if open_pos.empty:
        return {}

    by_ticker = {t: g.sort_values("date") for t, g in bars.groupby("ticker")}
    reasons: dict[str, int] = {}

    for _, pos in open_pos.iterrows():
        g = by_ticker.get(pos["ticker"])
        if g is None or g.empty:
            continue
        entry_dt = _ts(pos["entry_date"])
        future = g[pd.to_datetime(g["date"]) > entry_dt]
        if future.empty:
            continue

        stop = pos["stop"]
        target = pos["target"]
        closed = False
        for _, row in future.iterrows():
            day = _ts(row["date"])
            hit = _exit_for_day(pos["direction"], row, stop, target)
            if hit is None and (day - entry_dt).days >= max_holding_days:
                hit = (float(row["close"]), "time")
            if hit is not None:
                exit_price, reason = hit
                close_side = _SIDES[pos["direction"].upper()][1]
                fill = broker.place(
                    Order(pos["ticker"], close_side, int(pos["qty"]), exit_price,
                          ts=day.date().isoformat())
                )
                state.close_position(
                    int(pos["id"]), fill.price, day.date().isoformat(), reason, fee=fill.fee
                )
                reasons[reason] = reasons.get(reason, 0) + 1
                closed = True
                break
        if not closed:
            continue

    return reasons


@dataclass
class BookSummary:
    open_count: int
    closed_count: int
    realized_pnl: float
    unrealized_pnl: float
    total_fees: float
    win_rate: float


def summarize(state: StateStore, bars: pd.DataFrame | None = None) -> BookSummary:
    """Aggregate the book. Unrealized P&L marks open positions to the latest
    close in `bars` (0 if bars not supplied)."""
    open_pos = state.get_positions("open")
    closed = state.get_positions("closed")

    unrealized = 0.0
    if bars is not None and not open_pos.empty:
        last_close = (
            bars.sort_values("date").groupby("ticker")["close"].last().to_dict()
        )
        for _, p in open_pos.iterrows():
            lc = last_close.get(p["ticker"])
            if lc is None:
                continue
            pnl, _ = _signed_pnl(p["direction"], p["entry_price"], float(lc), int(p["qty"]))
            unrealized += pnl

    wins = int((closed["pnl"] > 0).sum()) if not closed.empty else 0
    win_rate = wins / len(closed) if len(closed) else 0.0

    return BookSummary(
        open_count=len(open_pos),
        closed_count=len(closed),
        realized_pnl=state.realized_pnl(),
        unrealized_pnl=float(unrealized),
        total_fees=state.total_fees(),
        win_rate=win_rate,
    )


class PaperBook:
    """Convenience facade binding a `StateStore` + `Broker`."""

    def __init__(self, state: StateStore, broker: Broker):
        self.state = state
        self.broker = broker

    def open(self, recs: list, strategy: str) -> list[int]:
        return open_recommendations(self.state, self.broker, recs, strategy)

    def update(self, bars: pd.DataFrame, max_holding_days: int = 60) -> dict[str, int]:
        return update_positions(self.state, self.broker, bars, max_holding_days)

    def summary(self, bars: pd.DataFrame | None = None) -> BookSummary:
        return summarize(self.state, bars)
