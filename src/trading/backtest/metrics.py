from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

TRADING_DAYS = 252


@dataclass
class BacktestMetrics:
    total_return: float
    cagr: float
    vol: float
    sharpe: float
    max_drawdown: float
    monthly_win_rate: float
    n_days: int
    n_months: int


def compute_metrics(returns: pd.Series) -> BacktestMetrics:
    returns = returns.dropna()
    n = len(returns)
    if n == 0:
        return BacktestMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)

    total_return = float((1.0 + returns).prod() - 1.0)
    cagr = float((1.0 + total_return) ** (TRADING_DAYS / n) - 1.0) if n > 0 else 0.0
    sd = float(returns.std())
    vol = sd * np.sqrt(TRADING_DAYS)
    sharpe = (float(returns.mean()) / sd) * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0

    equity = (1.0 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1.0
    mdd = float(drawdown.min())

    monthly = (1.0 + returns).resample("ME").prod() - 1.0
    win_rate = float((monthly > 0).mean()) if len(monthly) > 0 else 0.0

    return BacktestMetrics(
        total_return=total_return,
        cagr=cagr,
        vol=vol,
        sharpe=sharpe,
        max_drawdown=mdd,
        monthly_win_rate=win_rate,
        n_days=n,
        n_months=int(len(monthly)),
    )


def annual_breakdown(returns: pd.Series) -> pd.DataFrame:
    """Per-calendar-year return / Sharpe / max drawdown / best & worst month."""
    returns = returns.dropna()
    if returns.empty:
        return pd.DataFrame(
            columns=["year", "return", "sharpe", "max_drawdown", "best_month", "worst_month", "n_days"]
        )

    rows = []
    for year, r in returns.groupby(returns.index.year):
        if len(r) == 0:
            continue
        total = float((1.0 + r).prod() - 1.0)
        sd = float(r.std())
        sharpe = (float(r.mean()) / sd) * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0
        equity = (1.0 + r).cumprod()
        mdd = float((equity / equity.cummax() - 1.0).min())
        monthly = (1.0 + r).resample("ME").prod() - 1.0
        rows.append(
            {
                "year": int(year),
                "return": total,
                "sharpe": sharpe,
                "max_drawdown": mdd,
                "best_month": float(monthly.max()) if len(monthly) else 0.0,
                "worst_month": float(monthly.min()) if len(monthly) else 0.0,
                "n_days": int(len(r)),
            }
        )
    return pd.DataFrame(rows).set_index("year")
