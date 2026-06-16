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


def stop_and_target(direction: str, entry: float, stop_dist: float, reward_risk: float) -> tuple:
    """Direction-aware stop/target. Long: stop below, target above. Short: mirrored."""
    if direction.upper() == "SHORT":
        return entry + stop_dist, entry - reward_risk * stop_dist
    return entry - stop_dist, entry + reward_risk * stop_dist


def _allocate(candidates: list[dict], risk: RiskConfig) -> None:
    """Size shares across candidates in-place (direction-agnostic — sizing keys off
    `entry` and `stop_dist`, which hold for both longs and shorts).

    `equal_weight`: starts each at min(slot_cap, risk_ceiling), then runs a
    priority-ordered spillover loop that adds shares one at a time to the
    highest-priority candidates that still fit, bounded by the risk ceiling and
    `max_position_pct`. Priority = conviction, tie-broken by signal strength.
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
    ranked = sorted(candidates, key=lambda c: -c["priority"])

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


def _make_candidate(
    ticker: str,
    g: pd.DataFrame,
    score: float,
    rank: int,
    direction: str,
    conviction: int,
    risk: RiskConfig,
    as_of: pd.Timestamp,
) -> dict | None:
    entry = float(g["close"].iloc[-1])
    atr = _atr(g)
    if atr is None or atr <= 0:
        return None
    stop_dist = risk.atr_stop_multiple * atr
    return {
        "ticker": ticker,
        "direction": direction,
        "entry": entry,
        "atr": atr,
        "stop_dist": stop_dist,
        "score": score,
        "rank": rank,
        "conviction": conviction,
        # spillover priority: conviction dominates, signal magnitude breaks ties.
        "priority": float(conviction) + min(abs(score), 0.999),
        "as_of": as_of,
        "shares": 0,
    }


def _sizing_note(risk: RiskConfig) -> str:
    if risk.sizing_mode == "equal_weight":
        return (
            f"equal-weight slot (₹{risk.capital_inr / risk.max_positions:,.0f}) + "
            f"priority spillover, risk ceiling {risk.max_risk_per_trade_pct * 100:.1f}%, "
            f"position cap {risk.max_position_pct * 100:.0f}%"
        )
    return f"{risk.risk_per_trade_pct * 100:.1f}% risk-per-trade"


def build_recommendations(
    bars: pd.DataFrame,
    risk: RiskConfig,
    top_n: int = 10,
    short_n: int = 0,
    short_max_score: float = 0.0,
) -> list[Recommendation]:
    """Cross-sectional 12-1 momentum recommendations.

    Longs: the `top_n` strongest names. Shorts (when `short_n > 0`): the weakest
    `short_n` names whose momentum is below `short_max_score` (default: only short
    names with negative momentum). Shorts get mirrored stops/targets.
    """
    momentum = momentum_12_1(bars)
    if momentum.empty:
        return []

    by_ticker = {t: g.sort_values("date") for t, g in bars.groupby("ticker")}
    candidates: list[dict] = []

    # ---- long sleeve -----------------------------------------------------
    for _, row in momentum.head(top_n).iterrows():
        g = by_ticker.get(row["ticker"])
        if g is None or g.empty:
            continue
        rank = int(row["rank"])
        conviction = max(1, min(5, 6 - rank))
        c = _make_candidate(
            row["ticker"], g, float(row["score"]), rank, "LONG", conviction,
            risk, pd.Timestamp(row["as_of"]),
        )
        if c is not None:
            candidates.append(c)

    # ---- short sleeve (laggards) ----------------------------------------
    if short_n > 0:
        worst = momentum[momentum["score"] < short_max_score].tail(short_n)
        # most-negative first → highest short conviction
        worst = worst.iloc[::-1].reset_index(drop=True)
        for srank, (_, row) in enumerate(worst.iterrows(), start=1):
            g = by_ticker.get(row["ticker"])
            if g is None or g.empty:
                continue
            conviction = max(1, min(5, 6 - srank))
            c = _make_candidate(
                row["ticker"], g, float(row["score"]), srank, "SHORT", conviction,
                risk, pd.Timestamp(row["as_of"]),
            )
            if c is not None:
                candidates.append(c)

    _allocate(candidates, risk)

    sizing_note = _sizing_note(risk)
    recs: list[Recommendation] = []
    for c in candidates:
        if c["shares"] <= 0:
            continue
        entry, stop_dist = c["entry"], c["stop_dist"]
        stop, target = stop_and_target(c["direction"], entry, stop_dist, risk.reward_risk_ratio)
        notional = c["shares"] * entry
        risk_inr = c["shares"] * stop_dist

        if c["direction"] == "SHORT":
            rationale = (
                f"Cross-sectional 12-1 momentum laggard (#{c['rank']} weakest, "
                f"score {c['score'] * 100:.1f}%, ATR(14) ₹{c['atr']:.2f}). "
                f"Short at last close; stop at {risk.atr_stop_multiple:g}× ATR above; "
                f"target at {risk.reward_risk_ratio:g}× risk below. Sized via {sizing_note}."
            )
        else:
            rationale = (
                f"Cross-sectional 12-1 momentum rank #{c['rank']} "
                f"(score {c['score'] * 100:.1f}%, ATR(14) ₹{c['atr']:.2f}). "
                f"Entry at last close; stop at {risk.atr_stop_multiple:g}× ATR; "
                f"target at {risk.reward_risk_ratio:g}× risk. Sized via {sizing_note}."
            )

        recs.append(
            Recommendation(
                ticker=c["ticker"],
                direction=c["direction"],
                entry=entry,
                stop=stop,
                target=target,
                shares=c["shares"],
                notional=notional,
                risk_inr=risk_inr,
                conviction=c["conviction"],
                score=c["score"],
                as_of=c["as_of"],
                rationale=rationale,
            )
        )

    # longs by descending score, then shorts by ascending (most negative) score
    def _sort_key(r: Recommendation) -> tuple:
        is_short = r.direction == "SHORT"
        return (is_short, r.score if is_short else -r.score)

    recs.sort(key=_sort_key)
    return recs
