from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def add_compression_signals(
    g: pd.DataFrame,
    nr_lookback: int = 7,
    atr_period: int = 14,
    sma_period: int = 200,
    vol_lookback: int = 20,
) -> pd.DataFrame:
    """Annotate a single-ticker bar series with compression-pattern flags + filters.

    NR7: today's range is the smallest in the last `nr_lookback` days (inclusive).
    Inside day: today's high < yesterday's high AND today's low > yesterday's low.
    Also computes SMA(`sma_period`) for trend filter and volume_ratio for volume filter.
    """
    g = g.sort_values("date").copy()
    rng = g["high"] - g["low"]
    g["range"] = rng
    g["range_min_n"] = rng.rolling(nr_lookback).min()
    g["is_nr7"] = (rng <= g["range_min_n"]).fillna(False)

    g["prev_high"] = g["high"].shift(1)
    g["prev_low"] = g["low"].shift(1)
    g["is_inside"] = ((g["high"] < g["prev_high"]) & (g["low"] > g["prev_low"])).fillna(False)

    g["atr"] = ta.atr(g["high"], g["low"], g["close"], length=atr_period)
    g["sma_trend"] = g["close"].rolling(sma_period).mean()
    g["volume_ratio"] = g["volume"] / g["volume"].rolling(vol_lookback).mean()
    return g
