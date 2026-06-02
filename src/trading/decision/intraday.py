from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading.config.settings import RiskConfig
from trading.signals.intraday_setups import add_compression_signals


@dataclass
class IntradayIdea:
    ticker: str
    setup: str  # "NR7", "InsideDay", "NR7+InsideDay"
    ref_close: float
    breakout: float        # long trigger (today's high)
    breakdown: float       # short trigger (today's low)
    long_stop: float       # = breakdown
    long_target: float     # breakout + reward_mult × ATR
    short_stop: float      # = breakout
    short_target: float    # breakdown - reward_mult × ATR
    today_range: float
    atr: float
    compression: float     # atr / today_range — higher = tighter
    long_shares: int
    short_shares: int
    risk_inr_long: float
    as_of: pd.Timestamp


def _shares_risk_based(stop_dist: float, capital: float, risk_pct: float) -> int:
    if stop_dist <= 0:
        return 0
    return max(0, int((capital * risk_pct) // stop_dist))


def build_intraday_watchlist(
    bars: pd.DataFrame,
    risk: RiskConfig,
    top_n: int = 15,
    reward_atr_multiple: float = 1.5,
    min_volume_ratio: float = 1.5,
    prefer_inside_day: bool = True,
) -> list[IntradayIdea]:
    """Scan today's bars for compression setups; return ranked next-day watchlist.

    Filters applied (from the salvage backtest):
      - Volume on the compression day ≥ `min_volume_ratio` × 20d avg volume.
      - Optionally `prefer_inside_day`: Inside Day setups outranked NR7-only in backtest;
        included as a sort key but NR7-only still appears (lower rank).
    Long setup: enter on break above today's high; stop at today's low; target = breakout + reward × ATR.
    """
    ideas: list[IntradayIdea] = []

    for ticker, g in bars.groupby("ticker"):
        g = add_compression_signals(g.sort_values("date"))
        last = g.iloc[-1]
        nr7 = bool(last["is_nr7"])
        inside = bool(last["is_inside"])
        if not (nr7 or inside):
            continue
        vr = last.get("volume_ratio")
        if vr is None or pd.isna(vr) or vr < min_volume_ratio:
            continue
        atr = last["atr"]
        if pd.isna(atr) or atr <= 0:
            continue
        atr = float(atr)
        breakout = float(last["high"])
        breakdown = float(last["low"])
        ref_close = float(last["close"])
        today_range = breakout - breakdown
        if today_range <= 0:
            continue

        long_stop_dist = breakout - breakdown          # break long entry to today's low
        short_stop_dist = breakout - breakdown          # break short entry to today's high
        long_target = breakout + reward_atr_multiple * atr
        short_target = breakdown - reward_atr_multiple * atr
        compression = atr / today_range if today_range > 0 else 0.0

        long_shares = _shares_risk_based(long_stop_dist, risk.capital_inr, risk.risk_per_trade_pct)
        short_shares = _shares_risk_based(short_stop_dist, risk.capital_inr, risk.risk_per_trade_pct)

        setup_parts = []
        if nr7:
            setup_parts.append("NR7")
        if inside:
            setup_parts.append("InsideDay")
        setup = "+".join(setup_parts)

        ideas.append(
            IntradayIdea(
                ticker=ticker,
                setup=setup,
                ref_close=ref_close,
                breakout=breakout,
                breakdown=breakdown,
                long_stop=breakdown,
                long_target=long_target,
                short_stop=breakout,
                short_target=short_target,
                today_range=today_range,
                atr=atr,
                compression=compression,
                long_shares=long_shares,
                short_shares=short_shares,
                risk_inr_long=long_shares * long_stop_dist,
                as_of=pd.Timestamp(last["date"]),
            )
        )

    def _sort_key(i: IntradayIdea) -> tuple:
        inside_bonus = 1 if (prefer_inside_day and "InsideDay" in i.setup) else 0
        return (-inside_bonus, -i.compression)

    ideas.sort(key=_sort_key)
    return ideas[:top_n]
