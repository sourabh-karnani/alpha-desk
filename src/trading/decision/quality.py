from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pandas_ta as ta

from trading.storage.fundamentals import FundamentalsStore

# Filter thresholds — tuned to exclude bubble names (INTC-style) and loss-makers.
MIN_MOMENTUM = 0.0          # positive 12-1 momentum required
MIN_TRAILING_EPS = 0.0      # must be profitable on a TTM basis
MIN_FORWARD_PE = 2.0        # below this is usually a data anomaly
MAX_FORWARD_PE = 40.0       # bubble cap (semis peer avg ~25; allow growth premium)
MAX_EXTENSION = 0.50        # close ≤ 1.5 × SMA(200), i.e. not >50% above trend
MAX_RSI = 70.0              # not overbought


@dataclass
class QualityCandidate:
    ticker: str
    short_name: str | None
    close: float
    momentum: float          # 12-1 momentum (raw, e.g., 0.27 = +27%)
    rsi: float
    sma200: float
    extension_pct: float     # (close / sma200) - 1
    atr: float
    sector: str | None
    industry: str | None
    market_cap: float | None
    forward_pe: float | None
    trailing_eps: float | None
    profit_margin: float | None
    roe: float | None
    revenue_growth: float | None
    analyst_target: float | None
    analyst_rec: str | None
    fifty_two_week_high: float | None
    fifty_two_week_low: float | None
    checks: dict[str, bool] = field(default_factory=dict)
    passed_all: bool = False


def _is_num(x) -> bool:
    return x is not None and not pd.isna(x)


def confidence_stars(c: QualityCandidate) -> int:
    """1-5 stars, summed from bonus signals beyond minimum filter thresholds. Max raw = 12."""
    score = 0
    # Momentum strength (max 2)
    if c.momentum > 0.5:
        score += 2
    elif c.momentum > 0.25:
        score += 1
    # Valuation (max 2)
    if _is_num(c.forward_pe):
        if c.forward_pe < 15:
            score += 2
        elif c.forward_pe < 25:
            score += 1
    # Margins (max 2)
    if _is_num(c.profit_margin):
        if c.profit_margin > 0.20:
            score += 2
        elif c.profit_margin > 0.10:
            score += 1
    # Analyst upside (max 2)
    if _is_num(c.analyst_target) and c.close > 0:
        ups = c.analyst_target / c.close - 1
        if ups > 0.10:
            score += 2
        elif ups > 0:
            score += 1
    # Not too extended (max 2)
    if c.extension_pct < 0.15:
        score += 2
    elif c.extension_pct < 0.30:
        score += 1
    # RSI in healthy range (max 2)
    if 35 <= c.rsi < 60:
        score += 2
    elif c.rsi < 65:
        score += 1

    if score >= 10:
        return 5
    if score >= 8:
        return 4
    if score >= 6:
        return 3
    if score >= 4:
        return 2
    return 1


REC_KEY_SCORE = {
    "strong_buy": 10,
    "buy": 8,
    "outperform": 7,
    "hold": 4,
    "neutral": 4,
    "underperform": 1,
    "sell": 0,
    "strong_sell": 0,
}


def fundamental_score(c: QualityCandidate) -> int:
    """0-25. Cheap + quality."""
    s = 0
    if _is_num(c.forward_pe):
        if c.forward_pe < 15:
            s += 8
        elif c.forward_pe < 25:
            s += 5
        elif c.forward_pe < 40:
            s += 2
    if _is_num(c.profit_margin):
        if c.profit_margin > 0.25:
            s += 6
        elif c.profit_margin > 0.15:
            s += 4
        elif c.profit_margin > 0.05:
            s += 2
    if _is_num(c.roe):
        if c.roe > 0.25:
            s += 6
        elif c.roe > 0.15:
            s += 4
        elif c.roe > 0.05:
            s += 2
    if _is_num(c.revenue_growth):
        if c.revenue_growth > 0.15:
            s += 5
        elif c.revenue_growth > 0.05:
            s += 3
        elif c.revenue_growth > 0:
            s += 1
    return min(s, 25)


def technical_score(c: QualityCandidate) -> int:
    """0-25. Trend health, not extended, low vol."""
    s = 0
    if c.close > c.sma200:
        s += 8
    if 40 <= c.rsi <= 65:
        s += 6
    elif 35 <= c.rsi < 70:
        s += 3
    if c.extension_pct < 0.15:
        s += 6
    elif c.extension_pct < 0.30:
        s += 3
    atr_pct = c.atr / c.close if c.close > 0 else 1.0
    if atr_pct < 0.025:
        s += 5
    elif atr_pct < 0.04:
        s += 3
    elif atr_pct < 0.06:
        s += 1
    return min(s, 25)


def momentum_score(c: QualityCandidate) -> int:
    """0-25. Price-based persistence, with a cap on bubble momentum."""
    s = 0
    m = c.momentum
    if m > 1.0:
        s += 10  # capped — suspicious of extreme runs
    elif m > 0.6:
        s += 15
    elif m > 0.3:
        s += 10
    elif m > 0.15:
        s += 5
    elif m > 0:
        s += 2
    if _is_num(c.fifty_two_week_high) and c.close > 0:
        dist_high = c.close / c.fifty_two_week_high - 1
        if -0.10 < dist_high < -0.02:
            s += 5
        elif -0.20 < dist_high <= -0.10:
            s += 3
        elif dist_high >= -0.02:
            s += 2
    if 0.05 < c.extension_pct < 0.25:
        s += 5
    elif c.extension_pct > 0.25:
        s += 2
    return min(s, 25)


def analyst_score(c: QualityCandidate) -> int:
    """0-25. Sell-side target + rating."""
    s = 0
    if _is_num(c.analyst_target) and c.close > 0:
        ups = c.analyst_target / c.close - 1
        if ups > 0.25:
            s += 12
        elif ups > 0.15:
            s += 10
        elif ups > 0.05:
            s += 6
        elif ups > 0:
            s += 3
    if c.analyst_rec:
        s += REC_KEY_SCORE.get(c.analyst_rec.lower(), 4)
    return min(s, 25)


def composite_scores(c: QualityCandidate) -> dict[str, int]:
    f = fundamental_score(c)
    t = technical_score(c)
    m = momentum_score(c)
    a = analyst_score(c)
    return {"fundamental": f, "technical": t, "momentum": m, "analyst": a, "total": f + t + m + a}


def composite_picks(
    bars: pd.DataFrame,
    store: FundamentalsStore,
    top_n: int = 10,
    max_per_sector: int = 3,
    min_total_score: int = 50,
) -> tuple[list[tuple[QualityCandidate, dict]], list[tuple[QualityCandidate, dict]]]:
    """Rank by 4-factor composite. Hard filters from `quality_picks` still apply
    (must be profitable, in uptrend, reasonable P/E, not extreme). Within survivors,
    rank by composite total (0-100), sector-cap, take top N.
    """
    candidates: list[tuple[QualityCandidate, dict]] = []
    for ticker, g in bars.groupby("ticker"):
        fund = store.get(ticker)
        if fund is None:
            continue
        c = _evaluate(ticker, g, fund)
        if c is None:
            continue
        scores = composite_scores(c)
        candidates.append((c, scores))

    passing = [(c, sc) for c, sc in candidates if c.passed_all and sc["total"] >= min_total_score]
    passing.sort(key=lambda x: -x[1]["total"])

    sector_counts: dict[str, int] = {}
    picks: list[tuple[QualityCandidate, dict]] = []
    for c, sc in passing:
        sec = c.sector or "Unknown"
        if sector_counts.get(sec, 0) >= max_per_sector:
            continue
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        picks.append((c, sc))
        if len(picks) >= top_n:
            break

    return picks, candidates


def buy_reason(c: QualityCandidate) -> str:
    """Compose a 1-sentence rationale from the candidate's metrics."""
    parts: list[str] = []

    # Momentum
    if c.momentum >= 1.0:
        parts.append(f"massive momentum (+{c.momentum * 100:.0f}%)")
    elif c.momentum >= 0.5:
        parts.append(f"strong momentum (+{c.momentum * 100:.0f}%)")
    elif c.momentum >= 0.25:
        parts.append(f"solid momentum (+{c.momentum * 100:.0f}%)")
    else:
        parts.append(f"positive momentum (+{c.momentum * 100:.0f}%)")

    # Valuation
    if _is_num(c.forward_pe):
        if c.forward_pe < 12:
            parts.append(f"deeply cheap (P/E {c.forward_pe:.1f})")
        elif c.forward_pe < 20:
            parts.append(f"attractive (P/E {c.forward_pe:.1f})")
        elif c.forward_pe < 30:
            parts.append(f"reasonable P/E {c.forward_pe:.1f}")
        else:
            parts.append(f"growth premium (P/E {c.forward_pe:.1f})")

    # Quality
    if _is_num(c.profit_margin):
        if c.profit_margin >= 0.25:
            parts.append(f"exceptional margins ({c.profit_margin * 100:.0f}%)")
        elif c.profit_margin >= 0.15:
            parts.append(f"high margins ({c.profit_margin * 100:.0f}%)")
        elif c.profit_margin > 0.05:
            parts.append(f"profitable ({c.profit_margin * 100:.0f}% margin)")

    # Analyst view
    if _is_num(c.analyst_target) and c.close > 0:
        ups = c.analyst_target / c.close - 1
        if ups > 0.15:
            parts.append(f"+{ups * 100:.0f}% analyst upside")
        elif ups > 0.05:
            parts.append(f"+{ups * 100:.0f}% analyst upside")
        elif ups < -0.05:
            parts.append(f"-{abs(ups) * 100:.0f}% analyst downside (caution)")

    # Technical caveats
    if c.rsi >= 65 or c.extension_pct >= 0.35:
        parts.append("⚠ extended/near overbought")
    elif c.rsi < 45 and c.extension_pct < 0.15:
        parts.append("entry edge (uptrend, not extended)")

    return "; ".join(parts) + "."


def _evaluate(ticker: str, bars_g: pd.DataFrame, fund: dict) -> QualityCandidate | None:
    g = bars_g.sort_values("date")
    if len(g) < 253:
        return None

    closes_adj = g["adj_close"].to_numpy()
    if closes_adj[-253] <= 0:
        return None
    momentum = float(closes_adj[-22] / closes_adj[-253] - 1.0)

    last = g.iloc[-1]
    sma200_series = g["close"].rolling(200).mean()
    sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else None
    rsi_series = ta.rsi(g["close"], length=14)
    rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and not rsi_series.empty else None
    atr_series = ta.atr(g["high"], g["low"], g["close"], length=14)
    atr = float(atr_series.iloc[-1]) if atr_series is not None and not atr_series.empty else None

    close = float(last["close"])
    if sma200 is None or rsi is None or atr is None:
        return None
    extension = close / sma200 - 1.0

    forward_pe = fund.get("forward_pe")
    trailing_eps = fund.get("trailing_eps")

    checks = {
        "momentum_positive": momentum > MIN_MOMENTUM,
        "profitable_ttm": (trailing_eps is not None) and (trailing_eps > MIN_TRAILING_EPS),
        "reasonable_pe": (
            (forward_pe is not None) and (MIN_FORWARD_PE <= forward_pe <= MAX_FORWARD_PE)
        ),
        "above_sma200": close > sma200,
        "not_extended": extension < MAX_EXTENSION,
        "not_overbought": rsi < MAX_RSI,
    }

    return QualityCandidate(
        ticker=ticker,
        short_name=fund.get("short_name"),
        close=close,
        momentum=momentum,
        rsi=rsi,
        sma200=sma200,
        extension_pct=extension,
        atr=atr,
        sector=fund.get("sector"),
        industry=fund.get("industry"),
        market_cap=fund.get("market_cap"),
        forward_pe=forward_pe,
        trailing_eps=trailing_eps,
        profit_margin=fund.get("profit_margin"),
        roe=fund.get("roe"),
        revenue_growth=fund.get("revenue_growth"),
        analyst_target=fund.get("analyst_target"),
        analyst_rec=fund.get("analyst_recommendation"),
        fifty_two_week_high=fund.get("fifty_two_week_high"),
        fifty_two_week_low=fund.get("fifty_two_week_low"),
        checks=checks,
        passed_all=all(checks.values()),
    )


def quality_picks(
    bars: pd.DataFrame,
    store: FundamentalsStore,
    top_n: int = 10,
    max_per_sector: int = 3,
) -> tuple[list[QualityCandidate], list[QualityCandidate]]:
    """Returns (filtered_picks, all_candidates).

    `filtered_picks`: passes every filter, sector-capped at `max_per_sector`,
    ranked by momentum, truncated to `top_n`.
    `all_candidates`: every name we could evaluate (with check flags), for
    transparency on near-misses.
    """
    all_candidates: list[QualityCandidate] = []
    for ticker, g in bars.groupby("ticker"):
        fund = store.get(ticker)
        if fund is None:
            continue
        c = _evaluate(ticker, g, fund)
        if c is not None:
            all_candidates.append(c)

    passed = [c for c in all_candidates if c.passed_all]
    passed.sort(key=lambda c: -c.momentum)

    sector_counts: dict[str, int] = {}
    picks: list[QualityCandidate] = []
    for c in passed:
        sec = c.sector or "Unknown"
        if sector_counts.get(sec, 0) >= max_per_sector:
            continue
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        picks.append(c)
        if len(picks) >= top_n:
            break

    return picks, all_candidates
