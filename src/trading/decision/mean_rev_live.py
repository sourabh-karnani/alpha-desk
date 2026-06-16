"""Live mean-reversion recommender.

Bridges the mean-reversion *signal* (previously only reachable through the
backtester) into the same `Recommendation` surface the momentum recommender
uses, so `trading report --strategy mean_rev` produces actionable, sized,
direction-aware ideas for the next session.

A name is a candidate if, on its most recent bar, a fresh long entry (oversold
pullback in an uptrend) or — when ``allow_short`` is set — a fresh short entry
(overbought bounce in a downtrend) fires. Candidates are ranked by how far RSI
has stretched past the trigger (most-oversold / most-overbought first).
"""
from __future__ import annotations

import pandas as pd

from trading.config.settings import RiskConfig
from trading.decision.recommend import Recommendation, _allocate, stop_and_target
from trading.signals.mean_reversion import add_mean_rev_signals


def build_mean_rev_recommendations(
    bars: pd.DataFrame,
    risk: RiskConfig,
    top_n: int = 10,
    allow_short: bool = False,
    rsi_period: int = 14,
    rsi_entry: float = 30.0,
    rsi_exit: float = 60.0,
    short_rsi_entry: float = 70.0,
    short_rsi_exit: float = 40.0,
) -> list[Recommendation]:
    raw: list[dict] = []

    for ticker, g in bars.groupby("ticker"):
        gg = add_mean_rev_signals(
            g.sort_values("date"),
            rsi_period=rsi_period,
            rsi_entry=rsi_entry,
            rsi_exit=rsi_exit,
            short_rsi_entry=short_rsi_entry,
            short_rsi_exit=short_rsi_exit,
        )
        last = gg.iloc[-1]
        atr = last["atr"]
        rsi = last["rsi"]
        if pd.isna(atr) or atr <= 0 or pd.isna(rsi):
            continue

        direction: str | None = None
        if bool(last["entry_signal"]):
            direction = "LONG"
            edge = max(0.0, (rsi_entry - float(rsi))) / 100.0  # oversold depth
        elif allow_short and bool(last["short_entry_signal"]):
            direction = "SHORT"
            edge = max(0.0, (float(rsi) - short_rsi_entry)) / 100.0  # overbought stretch
        if direction is None:
            continue

        raw.append(
            {
                "ticker": ticker,
                "direction": direction,
                "entry": float(last["close"]),
                "atr": float(atr),
                "stop_dist": risk.atr_stop_multiple * float(atr),
                "rsi": float(rsi),
                "edge": edge,
                "as_of": pd.Timestamp(last["date"]),
                "shares": 0,
            }
        )

    if not raw:
        return []

    # Rank by edge (deepest stretch first); assign conviction + spillover priority.
    raw.sort(key=lambda c: -c["edge"])
    raw = raw[:top_n]
    for rank, c in enumerate(raw, start=1):
        c["rank"] = rank
        c["conviction"] = max(1, min(5, 6 - rank))
        c["score"] = c["edge"]
        c["priority"] = float(c["conviction"]) + min(c["edge"], 0.999)

    _allocate(raw, risk)

    recs: list[Recommendation] = []
    for c in raw:
        if c["shares"] <= 0:
            continue
        entry, stop_dist = c["entry"], c["stop_dist"]
        stop, target = stop_and_target(c["direction"], entry, stop_dist, risk.reward_risk_ratio)
        if c["direction"] == "SHORT":
            rationale = (
                f"Mean-reversion short: overbought bounce (RSI {c['rsi']:.0f} > "
                f"{short_rsi_entry:g}) in a downtrend (close < SMA200, SMA50 < SMA200). "
                f"Short at last close; stop {risk.atr_stop_multiple:g}× ATR(14) ₹{c['atr']:.2f} "
                f"above; target {risk.reward_risk_ratio:g}× risk below."
            )
        else:
            rationale = (
                f"Mean-reversion long: oversold pullback (RSI {c['rsi']:.0f} < "
                f"{rsi_entry:g}) in an uptrend (close > SMA200, SMA50 > SMA200). "
                f"Buy at last close; stop {risk.atr_stop_multiple:g}× ATR(14) ₹{c['atr']:.2f} "
                f"below; target {risk.reward_risk_ratio:g}× risk above."
            )
        recs.append(
            Recommendation(
                ticker=c["ticker"],
                direction=c["direction"],
                entry=entry,
                stop=stop,
                target=target,
                shares=c["shares"],
                notional=c["shares"] * entry,
                risk_inr=c["shares"] * stop_dist,
                conviction=c["conviction"],
                score=c["score"],
                as_of=c["as_of"],
                rationale=rationale,
            )
        )

    recs.sort(key=lambda r: -r.conviction)
    return recs
