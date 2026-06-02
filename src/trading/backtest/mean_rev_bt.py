from __future__ import annotations

import pandas as pd

from trading.backtest.per_asset import backtest_per_asset
from trading.backtest.portfolio import BacktestResult
from trading.signals.mean_reversion import add_mean_rev_signals


def run(
    bars: pd.DataFrame,
    max_concurrent: int = 10,
    stop_atr_mult: float = 2.0,
    max_holding_days: int = 30,
    cost_bps: float = 15.0,
    initial_capital: float = 100_000.0,
    rsi_period: int = 14,
    rsi_entry: float = 30.0,
    rsi_exit: float = 60.0,
) -> BacktestResult:
    def _signals(g: pd.DataFrame) -> pd.DataFrame:
        return add_mean_rev_signals(
            g,
            rsi_period=rsi_period,
            rsi_entry=rsi_entry,
            rsi_exit=rsi_exit,
        )

    return backtest_per_asset(
        bars=bars,
        signal_fn=_signals,
        max_concurrent=max_concurrent,
        stop_atr_mult=stop_atr_mult,
        max_holding_days=max_holding_days,
        cost_bps=cost_bps,
        initial_capital=initial_capital,
    )
