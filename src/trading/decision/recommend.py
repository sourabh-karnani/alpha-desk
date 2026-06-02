from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pandas_ta as ta

from trading.config.settings import RiskConfig
from trading.signals.momentum import momentum_12_1


@dataclass
class Recommendation:
    ticker: str
    direction: str
    entry: float
    stop: float
    target: float
    shares: int
    notional: float
    risk_inr: float
    conviction: int
    score: float
    as_of: pd.Timestamp
    rationale: str


def _atr(g: pd.DataFrame, period: int = 14) -> float | None:
    if len(g) < period + 1:
        return None
    series = ta.atr(high=g["high"], low=g["low"], close=g["close"], length=period)
    if series is None or series.empty:
        return None
    val = series.iloc[-1]
    return None if pd.isna(val) else float(val)


def _allocate(candidates: list[dict], risk: RiskConfig) -> None:
    """Size shares across candidates in-place.

    `equal_weight`: starts each at min(slot_cap, risk_ceiling), then runs a
    rank-priority spillover loop that adds shares one at a time to the highest-
    score candidates that still fit, bounded by risk ceiling and `max_position_pct`.
    `risk_based`: classic 1%-per-trade sizing, no spillover.
    """
    if not candidates:
        return

    risk_ceiling = risk.capital_inr * risk.max_risk_per_trade_pct
    slot_cap = risk.capital_inr / risk.max_positions
    abs_cap = risk.capital_inr * risk.max_position_pct

    for c in candidates:
        if risk.sizing_mode == "risk_based":
            budget = risk.capital_inr * risk.risk_per_trade_pct
            c["shares"] = max(0, int(budget // c["stop_dist"]))
        else:
            c["shares"] = max(
                0,
                min(
                    int(slot_cap // c["entry"]),
                    int(risk_ceiling // c["stop_dist"]),
                ),
            )

    if risk.sizing_mode == "risk_based":
        return

    used = sum(c["shares"] * c["entry"] for c in candidates)
    ranked = sorted(candidates, key=lambda c: -c["score"])

    progressed = True
    while progressed:
        progressed = False
        for c in ranked:
            remaining = risk.capital_inr - used
            if c["entry"] > remaining:
                continue
            new_shares = c["shares"] + 1
            if new_shares * c["stop_dist"] > risk_ceiling:
                continue
            if new_shares * c["entry"] > abs_cap:
                continue
            c["shares"] = new_shares
            used += c["entry"]
            progressed = True


def build_recommendations(
    bars: pd.DataFrame, risk: RiskConfig, top_n: int = 10
) -> list[Recommendation]:
    momentum = momentum_12_1(bars)
    if momentum.empty:
        return []

    by_ticker = {t: g.sort_values("date") for t, g in bars.groupby("ticker")}
    candidates: list[dict] = []

    for _, row in momentum.head(top_n).iterrows():
        ticker = row["ticker"]
        g = by_ticker.get(ticker)
        if g is None or g.empty:
            continue
        entry = float(g["close"].iloc[-1])
        atr = _atr(g)
        if atr is None or atr <= 0:
            continue
        stop_dist = risk.atr_stop_multiple * atr
        candidates.append(
            {
                "ticker": ticker,
                "entry": entry,
                "atr": atr,
                "stop_dist": stop_dist,
                "score": float(row["score"]),
                "rank": int(row["rank"]),
                "as_of": pd.Timestamp(row["as_of"]),
                "shares": 0,
            }
        )

    _allocate(candidates, risk)

    recs: list[Recommendation] = []
    for c in candidates:
        if c["shares"] <= 0:
            continue
        entry = c["entry"]
        stop_dist = c["stop_dist"]
        stop = entry - stop_dist
        target = entry + risk.reward_risk_ratio * stop_dist
        notional = c["shares"] * entry
        risk_inr = c["shares"] * stop_dist
        conviction = max(1, min(5, 6 - c["rank"]))

        if risk.sizing_mode == "equal_weight":
            sizing_note = (
                f"equal-weight slot (₹{risk.capital_inr / risk.max_positions:,.0f}) + "
                f"rank-priority spillover, risk ceiling {risk.max_risk_per_trade_pct * 100:.1f}%, "
                f"position cap {risk.max_position_pct * 100:.0f}%"
            )
        else:
            sizing_note = f"{risk.risk_per_trade_pct * 100:.1f}% risk-per-trade"

        rationale = (
            f"Cross-sectional 12-1 momentum rank #{c['rank']} "
            f"(score {c['score'] * 100:.1f}%, ATR(14) ₹{c['atr']:.2f}). "
            f"Entry at last close; stop at {risk.atr_stop_multiple:g}× ATR; "
            f"target at {risk.reward_risk_ratio:g}× risk. Sized via {sizing_note}."
        )
        recs.append(
            Recommendation(
                ticker=c["ticker"],
                direction="LONG",
                entry=entry,
                stop=stop,
                target=target,
                shares=c["shares"],
                notional=notional,
                risk_inr=risk_inr,
                conviction=conviction,
                score=c["score"],
                as_of=c["as_of"],
                rationale=rationale,
            )
        )

    recs.sort(key=lambda r: -r.score)
    return recs
