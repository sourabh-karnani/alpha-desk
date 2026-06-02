from __future__ import annotations

import pandas as pd

from trading.backtest.portfolio import BacktestResult, backtest_cross_sectional


def momentum_12_1_score(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.Series:
    """Cross-sectional 12-1 momentum score per ticker, computed on a wide price panel."""
    if len(prices) < lookback + 1:
        return pd.Series(dtype=float)
    end_p = prices.iloc[-skip - 1]
    start_p = prices.iloc[-(lookback + 1)]
    return (end_p / start_p - 1.0).where(start_p > 0)


def run(
    bars: pd.DataFrame,
    top_n: int = 10,
    initial_capital: float = 100_000.0,
    lookback: int = 252,
    skip: int = 21,
    cost_bps: float = 15.0,
    target_vol: float | None = None,
    vol_lookback: int = 60,
    max_leverage: float = 1.0,
) -> BacktestResult:
    return backtest_cross_sectional(
        bars=bars,
        score_fn=lambda h: momentum_12_1_score(h, lookback=lookback, skip=skip),
        top_n=top_n,
        min_history=lookback + 1,
        initial_capital=initial_capital,
        cost_bps=cost_bps,
        target_vol=target_vol,
        vol_lookback=vol_lookback,
        max_leverage=max_leverage,
    )
