from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series                              # post-cost equity curve
    returns: pd.Series                             # post-cost daily returns
    gross_returns: pd.Series                       # pre-cost daily returns
    costs: pd.Series                               # daily cost drag
    turnover: pd.Series | None = None              # cross-sectional only
    weights: pd.DataFrame | None = None            # cross-sectional only
    rebalance_dates: list[pd.Timestamp] | None = None  # cross-sectional only
    trades: pd.DataFrame | None = None             # per-asset only


ScoreFn = Callable[[pd.DataFrame], pd.Series]
"""Takes a wide price panel (date index, ticker columns) up to and including
a rebalance date, returns a score per ticker for that date."""


def _monthly_rebalance_dates(prices: pd.DataFrame) -> list[pd.Timestamp]:
    idx = pd.DatetimeIndex(prices.index)
    return list(idx.to_series().groupby(idx.to_period("M")).max().sort_values())


TRADING_DAYS = 252


def _apply_vol_targeting(
    gross_returns: pd.Series,
    costs: pd.Series,
    target_vol: float,
    vol_lookback: int,
    max_leverage: float,
) -> tuple[pd.Series, pd.Series]:
    """Scale daily returns + costs by trailing-vol-based leverage.

    leverage_t = min(max_leverage, target_vol / realized_vol_at_t-1).
    Costs scale with leverage too (fewer shares traded when scaled down).
    """
    if gross_returns.empty:
        return gross_returns, costs
    realized_vol = gross_returns.rolling(vol_lookback).std() * (TRADING_DAYS ** 0.5)
    leverage = (target_vol / realized_vol).clip(lower=0.0, upper=max_leverage)
    leverage = leverage.shift(1).fillna(1.0)
    return gross_returns * leverage, costs * leverage


def backtest_cross_sectional(
    bars: pd.DataFrame,
    score_fn: ScoreFn,
    top_n: int = 10,
    min_history: int = 253,
    initial_capital: float = 100_000.0,
    cost_bps: float = 15.0,
    target_vol: float | None = None,
    vol_lookback: int = 60,
    max_leverage: float = 1.0,
) -> BacktestResult:
    """Backtest a cross-sectional ranker with monthly rebalance, equal-weighted top N.

    Cost model: `cost_bps` is one-way trading cost in basis points, applied to
    the total turnover (sum of |Δweight|) at each rebalance. Going from cash to
    fully invested at the first rebalance counts as turnover 1.0 → 1.0×cost_bps.

    Weights known at end of rebalance day t are applied to returns from t+1 onward,
    so there is no look-ahead in the gross returns.
    """
    prices = (
        bars.pivot(index="date", columns="ticker", values="adj_close")
        .sort_index()
        .astype(float)
    )
    prices.index = pd.to_datetime(prices.index)

    rebal_all = _monthly_rebalance_dates(prices)

    weights = pd.DataFrame(index=prices.index, columns=prices.columns, dtype=float)
    turnover = pd.Series(0.0, index=prices.index)
    rebal_dates: list[pd.Timestamp] = []
    prev_w = pd.Series(0.0, index=prices.columns)

    for rd in rebal_all:
        history = prices.loc[:rd]
        if len(history) < min_history:
            continue
        score = score_fn(history).dropna()
        if score.empty:
            continue
        top = score.nlargest(top_n).index
        w = pd.Series(0.0, index=prices.columns)
        w[top] = 1.0 / len(top)
        weights.loc[rd] = w
        turnover.loc[rd] = float((w - prev_w).abs().sum())
        prev_w = w
        rebal_dates.append(rd)

    held = weights.ffill().fillna(0.0)
    daily_returns = prices.pct_change(fill_method=None).fillna(0.0)
    gross_returns = (held.shift(1).fillna(0.0) * daily_returns).sum(axis=1)

    cost_rate = cost_bps / 10000.0
    costs = turnover * cost_rate

    if rebal_dates:
        start = rebal_dates[0]
        gross_returns = gross_returns.loc[start:]
        costs = costs.loc[start:]
        turnover = turnover.loc[start:]

    if target_vol is not None:
        gross_returns, costs = _apply_vol_targeting(
            gross_returns, costs, target_vol, vol_lookback, max_leverage
        )

    net_returns = gross_returns - costs
    equity = (1.0 + net_returns).cumprod() * initial_capital

    return BacktestResult(
        equity=equity,
        returns=net_returns,
        gross_returns=gross_returns,
        costs=costs,
        turnover=turnover,
        weights=weights.loc[rebal_dates] if rebal_dates else weights.iloc[:0],
        rebalance_dates=rebal_dates,
    )
