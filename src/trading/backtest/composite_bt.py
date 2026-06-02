from __future__ import annotations

import pandas as pd
import pandas_ta as ta

from trading.backtest.portfolio import BacktestResult, _apply_vol_targeting
from trading.decision.quality import (
    MAX_EXTENSION,
    MAX_FORWARD_PE,
    MAX_RSI,
    MIN_FORWARD_PE,
    MIN_TRAILING_EPS,
    QualityCandidate,
    composite_scores,
)
from trading.storage.fundamentals import FundamentalsStore


def _monthly_rebalance_dates(idx: pd.DatetimeIndex) -> list[pd.Timestamp]:
    return list(idx.to_series().groupby(idx.to_period("M")).max().sort_values())


def run(
    bars: pd.DataFrame,
    store: FundamentalsStore | None = None,
    top_n: int = 10,
    max_per_sector: int = 3,
    initial_capital: float = 100_000.0,
    cost_bps: float = 15.0,
    min_total_score: int = 50,
    use_fundamentals: bool = True,
    target_vol: float | None = None,
    vol_lookback: int = 60,
    max_leverage: float = 1.0,
) -> BacktestResult:
    """Monthly-rebalance composite-ranking backtest.

    `use_fundamentals=False` → price-only (technical + momentum subscores, rescaled to /100).
        Rigorous, no lookahead.
    `use_fundamentals=True` → applies current fundamentals statically as both hard filters
        AND scoring inputs. **Lookahead caveat**: fundamentals don't time-vary in our data.
    """
    closes = bars.pivot(index="date", columns="ticker", values="close").sort_index().astype(float)
    closes.index = pd.to_datetime(closes.index)
    highs = bars.pivot(index="date", columns="ticker", values="high").sort_index().astype(float)
    highs.index = pd.to_datetime(highs.index)
    lows = bars.pivot(index="date", columns="ticker", values="low").sort_index().astype(float)
    lows.index = pd.to_datetime(lows.index)
    adj = bars.pivot(index="date", columns="ticker", values="adj_close").sort_index().astype(float)
    adj.index = pd.to_datetime(adj.index)

    rsi_dict: dict[str, pd.Series] = {}
    sma200_dict: dict[str, pd.Series] = {}
    atr_dict: dict[str, pd.Series] = {}
    for ticker in closes.columns:
        c = closes[ticker]
        rsi_dict[ticker] = ta.rsi(c, length=14)
        sma200_dict[ticker] = c.rolling(200).mean()
        atr_dict[ticker] = ta.atr(highs[ticker], lows[ticker], c, length=14)

    fund_data: dict[str, dict] = {}
    sector_of: dict[str, str] = {}
    if store is not None and use_fundamentals:
        for ticker in closes.columns:
            f = store.get(ticker)
            if f is not None:
                fund_data[ticker] = f
                sector_of[ticker] = f.get("sector") or "Unknown"

    rebal_all = _monthly_rebalance_dates(closes.index)
    weights = pd.DataFrame(index=closes.index, columns=closes.columns, dtype=float)
    turnover = pd.Series(0.0, index=closes.index)
    rebal_dates: list[pd.Timestamp] = []
    prev_w = pd.Series(0.0, index=closes.columns)

    for rd in rebal_all:
        if len(closes.loc[:rd]) < 253:
            continue

        candidates: list[tuple[str, int, str]] = []
        for ticker in closes.columns:
            c_hist = closes.loc[:rd, ticker].dropna()
            ac_hist = adj.loc[:rd, ticker].dropna()
            if len(c_hist) < 253 or len(ac_hist) < 253:
                continue

            close = float(c_hist.iloc[-1])
            sma200_v = sma200_dict[ticker].loc[:rd]
            if sma200_v.empty or pd.isna(sma200_v.iloc[-1]):
                continue
            sma200_val = float(sma200_v.iloc[-1])
            rsi_v = rsi_dict[ticker].loc[:rd]
            if rsi_v.empty or pd.isna(rsi_v.iloc[-1]):
                continue
            rsi_val = float(rsi_v.iloc[-1])
            atr_v = atr_dict[ticker].loc[:rd]
            if atr_v.empty or pd.isna(atr_v.iloc[-1]):
                continue
            atr_val = float(atr_v.iloc[-1])

            momentum = float(ac_hist.iloc[-22] / ac_hist.iloc[-253] - 1.0)
            extension = close / sma200_val - 1.0

            # Hard price-based filters
            if momentum <= 0:
                continue
            if close <= sma200_val:
                continue
            if extension >= MAX_EXTENSION:
                continue
            if rsi_val >= MAX_RSI:
                continue

            f = fund_data.get(ticker) if use_fundamentals else None
            if use_fundamentals:
                if f is None:
                    continue
                te = f.get("trailing_eps")
                fpe = f.get("forward_pe")
                if te is None or te <= MIN_TRAILING_EPS:
                    continue
                if fpe is None or not (MIN_FORWARD_PE <= fpe <= MAX_FORWARD_PE):
                    continue

            high_52w = float(c_hist.tail(252).max())
            low_52w = float(c_hist.tail(252).min())

            qc = QualityCandidate(
                ticker=ticker,
                short_name=None,
                close=close,
                momentum=momentum,
                rsi=rsi_val,
                sma200=sma200_val,
                extension_pct=extension,
                atr=atr_val,
                sector=sector_of.get(ticker, "Unknown"),
                industry=None,
                market_cap=None,
                forward_pe=(f or {}).get("forward_pe") if use_fundamentals else None,
                trailing_eps=(f or {}).get("trailing_eps") if use_fundamentals else None,
                profit_margin=(f or {}).get("profit_margin") if use_fundamentals else None,
                roe=(f or {}).get("roe") if use_fundamentals else None,
                revenue_growth=(f or {}).get("revenue_growth") if use_fundamentals else None,
                analyst_target=(f or {}).get("analyst_target") if use_fundamentals else None,
                analyst_rec=(f or {}).get("analyst_recommendation") if use_fundamentals else None,
                fifty_two_week_high=high_52w,
                fifty_two_week_low=low_52w,
            )
            sc = composite_scores(qc)
            total = sc["total"] if use_fundamentals else (sc["technical"] + sc["momentum"]) * 2

            if total < min_total_score:
                continue
            candidates.append((ticker, total, sector_of.get(ticker, "Unknown")))

        if not candidates:
            continue

        candidates.sort(key=lambda x: -x[1])
        sector_counts: dict[str, int] = {}
        chosen: list[str] = []
        for tkr, _, sec in candidates:
            if sector_counts.get(sec, 0) >= max_per_sector:
                continue
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            chosen.append(tkr)
            if len(chosen) >= top_n:
                break

        if not chosen:
            continue

        w = pd.Series(0.0, index=closes.columns)
        for tkr in chosen:
            w[tkr] = 1.0 / len(chosen)
        weights.loc[rd] = w
        turnover.loc[rd] = float((w - prev_w).abs().sum())
        prev_w = w
        rebal_dates.append(rd)

    held = weights.ffill().fillna(0.0)
    daily_returns = closes.pct_change(fill_method=None).fillna(0.0)
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
