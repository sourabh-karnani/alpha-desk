from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

from trading.decision.quality import (
    MAX_EXTENSION,
    MAX_FORWARD_PE,
    MAX_RSI,
    MIN_TRAILING_EPS,
    QualityCandidate,
    buy_reason,
    confidence_stars,
)


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%"


def _fmt_num(x: float | None, fmt: str = ".2f") -> str:
    if x is None:
        return "—"
    return format(x, fmt)


def render(
    picks: list[QualityCandidate],
    all_candidates: list[QualityCandidate],
    universe: str,
    max_per_sector: int,
    as_of: date | None = None,
) -> str:
    as_of = as_of or date.today()

    header = dedent(
        f"""\
        # Quality-Filtered Recommendations — {as_of.isoformat()}

        Universe: **{universe}**. Sector cap: max **{max_per_sector}** per sector.
        Paper-trade only — verify before any execution.

        ## Filters applied (must pass all)

        - Positive 12-1 momentum (`> 0`)
        - Profitable on TTM basis (`trailing_eps > {MIN_TRAILING_EPS}`)
        - Reasonable valuation (`forward P/E ≤ {MAX_FORWARD_PE:.0f}`)
        - In uptrend (`close > SMA(200)`)
        - Not extended (`close ≤ {1 + MAX_EXTENSION:.2f}× SMA(200)`)
        - Not overbought (`RSI(14) < {MAX_RSI:.0f}`)

        Ranked by momentum, then sector-capped.

        """
    )

    if not picks:
        return header + "**No names passed all filters.**\n"

    table = (
        "## Top picks\n\n"
        "| # | Ticker | Company | Sector | Close | Mom | P/E | RSI | Ext | **Confidence** | **Why** |\n"
        "|---|---|---|---|---:|---:|---:|---:|---:|:---:|---|\n"
    )
    for i, p in enumerate(picks, start=1):
        name = (p.short_name or p.ticker.replace(".NS", "").replace(".BO", ""))
        if len(name) > 28:
            name = name[:26] + "…"
        stars = "★" * confidence_stars(p)
        why = buy_reason(p)
        table += (
            f"| {i} | **{p.ticker}** | {name} | {p.sector or '—'} | "
            f"{p.close:.2f} | **{_fmt_pct(p.momentum)}** | "
            f"{_fmt_num(p.forward_pe, '.1f')} | "
            f"{_fmt_num(p.rsi, '.0f')} | "
            f"{_fmt_pct(p.extension_pct)} | "
            f"{stars} | {why} |\n"
        )

    summary = (
        f"\n**{len(picks)} pick(s)** from "
        f"**{sum(1 for c in all_candidates if c.passed_all)}** survivors out of "
        f"**{len(all_candidates)}** evaluable tickers.\n\n"
    )

    # Near-miss section: top-momentum names that failed at least one filter
    failed = [c for c in all_candidates if not c.passed_all]
    failed.sort(key=lambda c: -c.momentum)
    near_misses = failed[:15]
    if near_misses:
        nm = ["## Near misses — top momentum names that failed filters\n"]
        nm.append("| Ticker | Mom 12-1 | Failed checks |")
        nm.append("|---|---:|---|")
        for c in near_misses:
            failed_names = [k for k, v in c.checks.items() if not v]
            why = ", ".join(failed_names) if failed_names else "—"
            nm.append(f"| {c.ticker} | {_fmt_pct(c.momentum)} | {why} |")
        near_section = "\n".join(nm) + "\n"
    else:
        near_section = ""

    footer = (
        "\n---\n"
        "*Not investment advice. Quality filter is a defensive overlay on top of the 12-1 momentum signal — "
        "it removes loss-makers, bubble-valued names, and extended/overbought charts. It does NOT have its "
        "own backtested expectancy yet; treat results as discretionary guidance until a quality-aware "
        "backtest validates the exact rules.*\n"
    )
    return header + table + summary + near_section + footer


def write_report(text: str, reports_dir: Path, slug: str, as_of: date | None = None) -> Path:
    as_of = as_of or date.today()
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"quality_{slug}_{as_of.isoformat()}.md"
    path.write_text(text)
    return path
