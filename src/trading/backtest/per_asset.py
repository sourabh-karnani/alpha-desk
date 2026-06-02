from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from trading.backtest.portfolio import BacktestResult

SignalFn = Callable[[pd.DataFrame], pd.DataFrame]
"""Takes a single-ticker bar series, returns the same with added columns:
`rsi`, `atr`, `entry_signal` (bool), `exit_signal` (bool)."""


def backtest_per_asset(
    bars: pd.DataFrame,
    signal_fn: SignalFn,
    max_concurrent: int = 10,
    stop_atr_mult: float = 2.0,
    max_holding_days: int = 30,
    cost_bps: float = 15.0,
    initial_capital: float = 100_000.0,
) -> BacktestResult:
    """Per-asset signal-driven long-only backtest.

    At each date: mark-to-market open positions, check exits (stop/signal/time),
    then enter new positions from today's signals (most-oversold first by RSI),
    capped at `max_concurrent`. Each position is `1/max_concurrent` of capital.
    Idle slots earn 0 (cash, no rate).
    """
    enriched = []
    for _, g in bars.groupby("ticker"):
        enriched.append(signal_fn(g))
    bars = pd.concat(enriched).reset_index(drop=True)
    bars["date"] = pd.to_datetime(bars["date"])

    def _wide(col: str) -> pd.DataFrame:
        return bars.pivot(index="date", columns="ticker", values=col).sort_index()

    def _wide_bool(col: str) -> pd.DataFrame:
        df = _wide(col)
        return df.where(df.notna(), False).astype(bool)

    closes = _wide("close").astype(float)
    lows = _wide("low").astype(float)
    atrs = _wide("atr").astype(float)
    rsis = _wide("rsi").astype(float)
    entries = _wide_bool("entry_signal")
    exits = _wide_bool("exit_signal")

    daily_pct = closes.pct_change(fill_method=None).fillna(0.0)
    weight_per_pos = 1.0 / max_concurrent
    cost_rate = cost_bps / 10000.0

    open_positions: dict[str, dict] = {}
    trades: list[dict] = []
    daily_returns = pd.Series(0.0, index=closes.index)
    daily_costs = pd.Series(0.0, index=closes.index)

    for d in closes.index:
        # 1) Mark-to-market open positions
        for ticker, pos in open_positions.items():
            r = daily_pct.at[d, ticker] if ticker in daily_pct.columns else 0.0
            if pd.isna(r):
                r = 0.0
            daily_returns.at[d] += r * pos["weight"]

        # 2) Check exits
        to_close: list[tuple[str, str, float]] = []
        for ticker, pos in open_positions.items():
            today_low = lows.at[d, ticker] if ticker in lows.columns else float("nan")
            today_close = closes.at[d, ticker] if ticker in closes.columns else float("nan")
            today_exit = bool(exits.at[d, ticker]) if ticker in exits.columns else False
            holding_days = (d - pos["entry_date"]).days

            if pd.notna(today_low) and today_low <= pos["stop"]:
                to_close.append((ticker, "stop", pos["stop"]))
            elif today_exit:
                to_close.append((ticker, "signal", float(today_close)))
            elif holding_days >= max_holding_days:
                to_close.append((ticker, "time", float(today_close)))

        for ticker, reason, exit_price in to_close:
            pos = open_positions.pop(ticker)
            daily_costs.at[d] += cost_rate * pos["weight"]
            trades.append(
                {
                    "ticker": ticker,
                    "entry_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "exit_date": d,
                    "exit_price": exit_price,
                    "exit_reason": reason,
                    "weight": pos["weight"],
                    "pnl_pct": exit_price / pos["entry_price"] - 1.0,
                    "holding_days": (d - pos["entry_date"]).days,
                }
            )

        # 3) Enter new positions
        if len(open_positions) < max_concurrent:
            slots = max_concurrent - len(open_positions)
            today_entries = entries.loc[d]
            candidates = [t for t in today_entries.index if today_entries[t]]
            candidates = [t for t in candidates if t not in open_positions]
            ranked = []
            for t in candidates:
                rsi_v = rsis.at[d, t] if t in rsis.columns else float("nan")
                if pd.notna(rsi_v):
                    ranked.append((t, float(rsi_v)))
            ranked.sort(key=lambda x: x[1])  # most oversold first

            for t, _ in ranked[:slots]:
                entry_price = closes.at[d, t]
                atr = atrs.at[d, t]
                if pd.isna(entry_price) or pd.isna(atr) or atr <= 0:
                    continue
                stop = float(entry_price) - stop_atr_mult * float(atr)
                open_positions[t] = {
                    "entry_date": d,
                    "entry_price": float(entry_price),
                    "stop": stop,
                    "weight": weight_per_pos,
                }
                daily_costs.at[d] += cost_rate * weight_per_pos

    # Force-close any positions still open at the end (mark to last close)
    if open_positions:
        last_d = closes.index[-1]
        for ticker, pos in list(open_positions.items()):
            exit_price = float(closes.at[last_d, ticker])
            trades.append(
                {
                    "ticker": ticker,
                    "entry_date": pos["entry_date"],
                    "entry_price": pos["entry_price"],
                    "exit_date": last_d,
                    "exit_price": exit_price,
                    "exit_reason": "end",
                    "weight": pos["weight"],
                    "pnl_pct": exit_price / pos["entry_price"] - 1.0,
                    "holding_days": (last_d - pos["entry_date"]).days,
                }
            )

    net_returns = daily_returns - daily_costs
    if not net_returns.empty:
        first_active = net_returns.ne(0.0).idxmax() if net_returns.ne(0.0).any() else net_returns.index[0]
        net_returns = net_returns.loc[first_active:]
        daily_returns = daily_returns.loc[first_active:]
        daily_costs = daily_costs.loc[first_active:]
    equity = (1.0 + net_returns).cumprod() * initial_capital

    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        trades_df = trades_df.sort_values("entry_date").reset_index(drop=True)

    return BacktestResult(
        equity=equity,
        returns=net_returns,
        gross_returns=daily_returns,
        costs=daily_costs,
        trades=trades_df,
    )
