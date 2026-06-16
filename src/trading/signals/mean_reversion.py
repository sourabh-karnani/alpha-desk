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
    short_rsi_entry: float = 70.0,
    short_rsi_exit: float = 40.0,
) -> pd.DataFrame:
    """Annotate a single-ticker bar series with mean-reversion entry/exit signals.

    Long pullbacks (the default sleeve):
      Trend filter: close > SMA(slow) AND SMA(fast) > SMA(slow).
      Entry: RSI(period) crosses below `rsi_entry` while trend filter holds.
      Exit:  RSI(period) crosses above `rsi_exit`.

    Short bounces (mirror sleeve, used when shorts are enabled):
      Trend filter: close < SMA(slow) AND SMA(fast) < SMA(slow).
      Entry: RSI crosses above `short_rsi_entry` (overbought in a downtrend).
      Exit:  RSI crosses below `short_rsi_exit`.
    """
    g = g.sort_values("date").copy()
    g["sma_fast"] = g["close"].rolling(sma_fast).mean()
    g["sma_slow"] = g["close"].rolling(sma_slow).mean()
    g["rsi"] = ta.rsi(g["close"], length=rsi_period)
    g["atr"] = ta.atr(g["high"], g["low"], g["close"], length=atr_period)

    trend_up = (g["close"] > g["sma_slow"]) & (g["sma_fast"] > g["sma_slow"])
    rsi_below = g["rsi"] < rsi_entry
    rsi_below_prev = g["rsi"].shift(1) >= rsi_entry
    g["entry_signal"] = (trend_up & rsi_below & rsi_below_prev).fillna(False)

    rsi_above = g["rsi"] > rsi_exit
    rsi_above_prev = g["rsi"].shift(1) <= rsi_exit
    g["exit_signal"] = (rsi_above & rsi_above_prev).fillna(False)

    trend_down = (g["close"] < g["sma_slow"]) & (g["sma_fast"] < g["sma_slow"])
    s_rsi_above = g["rsi"] > short_rsi_entry
    s_rsi_above_prev = g["rsi"].shift(1) <= short_rsi_entry
    g["short_entry_signal"] = (trend_down & s_rsi_above & s_rsi_above_prev).fillna(False)

    s_rsi_below = g["rsi"] < short_rsi_exit
    s_rsi_below_prev = g["rsi"].shift(1) >= short_rsi_exit
    g["short_exit_signal"] = (s_rsi_below & s_rsi_below_prev).fillna(False)

    return g
