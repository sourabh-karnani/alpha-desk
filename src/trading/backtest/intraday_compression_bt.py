from __future__ import annotations

import pandas as pd

from trading.signals.intraday_setups import add_compression_signals

INTRADAY_COST_BPS_PER_SIDE = 8.0


def backtest_compression_long(
    bars: pd.DataFrame,
    reward_atr_multiple: float = 1.5,
    cost_bps_per_side: float = INTRADAY_COST_BPS_PER_SIDE,
    require_uptrend: bool = False,
    min_volume_ratio: float | None = None,
    exit_mode: str = "stop_target_close",
) -> tuple[pd.DataFrame, dict]:
    """Backtest long-only NR7 / Inside Day breakout using daily OHLC.

    Trigger: next-day high >= today's high → enter at today's high.
    Filters (optional, applied at setup day):
      - require_uptrend: close > SMA(200)
      - min_volume_ratio: volume / 20d avg volume >= threshold
    Exit modes:
      - "stop_target_close": stop at today's low; target at breakout + reward × ATR;
        otherwise exit at next-day close. Conservative when both levels hit (assume stop first).
      - "close_only": ignore stops and targets entirely; exit at next-day close.
    Costs: 2 × cost_bps_per_side round-trip.
    """
    trades: list[dict] = []

    for ticker, g in bars.groupby("ticker"):
        g = add_compression_signals(g.sort_values("date").reset_index(drop=True))
        for i in range(len(g) - 1):
            row = g.iloc[i]
            if not (bool(row["is_nr7"]) or bool(row["is_inside"])):
                continue
            atr = row["atr"]
            if pd.isna(atr) or atr <= 0:
                continue
            if require_uptrend:
                sma = row["sma_trend"]
                if pd.isna(sma) or row["close"] <= sma:
                    continue
            if min_volume_ratio is not None:
                vr = row["volume_ratio"]
                if pd.isna(vr) or vr < min_volume_ratio:
                    continue

            breakout = float(row["high"])
            breakdown = float(row["low"])
            target = breakout + reward_atr_multiple * float(atr)

            nxt = g.iloc[i + 1]
            n_high = float(nxt["high"])
            n_low = float(nxt["low"])
            n_close = float(nxt["close"])

            if n_high < breakout:
                continue

            entry = breakout

            if exit_mode == "close_only":
                exit_price, exit_reason = n_close, "close"
            else:
                stop_hit = n_low <= breakdown
                target_hit = n_high >= target
                if stop_hit and target_hit:
                    exit_price, exit_reason = breakdown, "stop"
                elif stop_hit:
                    exit_price, exit_reason = breakdown, "stop"
                elif target_hit:
                    exit_price, exit_reason = target, "target"
                else:
                    exit_price, exit_reason = n_close, "close"

            gross_pnl = exit_price / entry - 1.0
            pnl = gross_pnl - 2 * (cost_bps_per_side / 10000.0)

            setup_parts = []
            if bool(row["is_nr7"]):
                setup_parts.append("NR7")
            if bool(row["is_inside"]):
                setup_parts.append("InsideDay")

            trades.append(
                {
                    "ticker": ticker,
                    "setup_date": row["date"],
                    "trade_date": nxt["date"],
                    "setup": "+".join(setup_parts),
                    "entry": entry,
                    "stop": breakdown,
                    "target": target,
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_pct": pnl,
                    "gross_pnl_pct": gross_pnl,
                }
            )

    df = pd.DataFrame(trades)
    if df.empty:
        return df, {
            "n_trades": 0,
            "win_rate": 0.0,
            "avg_pnl_pct_net": 0.0,
            "avg_pnl_pct_gross": 0.0,
            "avg_win_pct": 0.0,
            "avg_loss_pct": 0.0,
            "exit_reasons": {},
        }

    wins = (df["pnl_pct"] > 0).sum()
    n = len(df)
    stats = {
        "n_trades": int(n),
        "win_rate": float(wins / n),
        "avg_pnl_pct_net": float(df["pnl_pct"].mean()),
        "avg_pnl_pct_gross": float(df["gross_pnl_pct"].mean()),
        "avg_win_pct": float(df.loc[df["pnl_pct"] > 0, "pnl_pct"].mean()) if wins else 0.0,
        "avg_loss_pct": float(df.loc[df["pnl_pct"] <= 0, "pnl_pct"].mean()) if n - wins else 0.0,
        "exit_reasons": df["exit_reason"].value_counts().to_dict(),
    }
    return df, stats
