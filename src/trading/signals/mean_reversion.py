from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def add_mean_rev_signals(
    g: pd.DataFrame,
    rsi_period: int = 14,
    rsi_entry: float = 30.0,
    rsi_exit: float = 60.0,
    sma_fast: int = 50,
    sma_slow: int = 200,
    atr_period: int = 14,
) -> pd.DataFrame:
    """Annotate a single-ticker bar series with mean-reversion entry/exit signals.

    Trend filter: close > SMA(slow) AND SMA(fast) > SMA(slow). Long-only pullbacks.
    Entry: RSI(period) crosses below `rsi_entry` while trend filter holds.
    Exit: RSI(period) crosses above `rsi_exit`.
    """
    g = g.sort_values("date").copy()
    g["sma_fast"] = g["close"].rolling(sma_fast).mean()
    g["sma_slow"] = g["close"].rolling(sma_slow).mean()
    g["rsi"] = ta.rsi(g["close"], length=rsi_period)
    g["atr"] = ta.atr(g["high"], g["low"], g["close"], length=atr_period)

    trend_ok = (g["close"] > g["sma_slow"]) & (g["sma_fast"] > g["sma_slow"])
    rsi_below = g["rsi"] < rsi_entry
    rsi_below_prev = g["rsi"].shift(1) >= rsi_entry
    g["entry_signal"] = (trend_ok & rsi_below & rsi_below_prev).fillna(False)

    rsi_above = g["rsi"] > rsi_exit
    rsi_above_prev = g["rsi"].shift(1) <= rsi_exit
    g["exit_signal"] = (rsi_above & rsi_above_prev).fillna(False)

    return g
