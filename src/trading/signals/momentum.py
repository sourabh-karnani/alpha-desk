from __future__ import annotations

import pandas as pd


def momentum_12_1(bars: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Cross-sectional 12-1 momentum.

    Score per ticker = price[t-skip] / price[t-lookback] - 1.
    Lookback default 252 trading days (~12 months); skip 21 (~1 month).
    Returns one row per ticker for the latest as_of, with score and rank.
    """
    if bars.empty:
        return pd.DataFrame(columns=["ticker", "score", "as_of", "rank"])

    bars = bars.sort_values(["ticker", "date"])
    results = []
    for ticker, g in bars.groupby("ticker"):
        if len(g) < lookback + 1:
            continue
        closes = g["adj_close"].to_numpy()
        end_close = closes[-skip - 1]
        start_close = closes[-(lookback + 1)]
        if start_close <= 0:
            continue
        score = float(end_close / start_close - 1.0)
        results.append(
            {"ticker": ticker, "score": score, "as_of": g["date"].iloc[-1]}
        )

    df = pd.DataFrame(results)
    if df.empty:
        return df
    df["rank"] = df["score"].rank(ascending=False, method="min").astype(int)
    return df.sort_values("rank").reset_index(drop=True)
