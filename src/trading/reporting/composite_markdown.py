from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import dedent

from trading.decision.quality import QualityCandidate, buy_reason


def _fmt_num(x: float | None, fmt: str = ".2f") -> str:
    if x is None:
        return "—"
    return format(x, fmt)


def render(
    picks: list[tuple[QualityCandidate, dict]],
    all_candidates: list[tuple[QualityCandidate, dict]],
    universe: str,
    max_per_sector: int,
    min_total_score: int,
    as_of: date | None = None,
) -> str:
    as_of = as_of or date.today()

    header = dedent(
        f"""\
        # Multi-Factor Composite Recommendations — {as_of.isoformat()}

        Universe: **{universe}**. Sector cap: max **{max_per_sector}** per sector. Min composite: **{min_total_score}**/100.
        Paper-trade only — verify before any execution.

        ## Methodology

        Mirrors how institutional quant funds (AQR, smart-beta ETFs) blend signals:

        | Factor | Max points | What it captures |
        |---|---:|---|
        | **Fundamental** (F) | 25 | Forward P/E + profit margin + ROE + revenue growth |
        | **Technical** (T) | 25 | Above SMA(200) + RSI band + not extended + low ATR |
        | **Momentum** (M) | 25 | 12-1 return + distance from 52w high + healthy extension |
        | **Analyst** (A) | 25 | Target vs price + recommendation key |
        | **Total** | **100** | Composite |

        Hard filters still apply (profitable TTM, in uptrend, P/E ≤ 40, RSI < 70).
        Survivors ranked by composite, then sector-capped.

        """
    )

    if not picks:
        return header + "**No names cleared all filters AND the minimum composite score.**\n"

    table = (
        "## Top picks\n\n"
        "| # | Ticker | Company | Sector | Close | F | T | M | A | **Total** | Why |\n"
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|\n"
    )
    for i, (p, sc) in enumerate(picks, start=1):
        name = p.short_name or p.ticker.replace(".NS", "").replace(".BO", "")
        if len(name) > 28:
            name = name[:26] + "…"
        why = buy_reason(p)
        table += (
            f"| {i} | **{p.ticker}** | {name} | {p.sector or '—'} | "
            f"{p.close:.2f} | {sc['fundamental']} | {sc['technical']} | "
            f"{sc['momentum']} | {sc['analyst']} | **{sc['total']}** | {why} |\n"
        )

    summary = (
        f"\n**{len(picks)} pick(s)** from "
        f"**{sum(1 for _, sc in all_candidates if sc['total'] >= min_total_score)}** "
        f"names that cleared score ≥ {min_total_score}, "
        f"out of **{len(all_candidates)}** evaluable.\n\n"
    )

    # Score distribution
    scored = sorted([sc["total"] for _, sc in all_candidates], reverse=True)
    if scored:
        median = scored[len(scored) // 2]
        distro = (
            "## Universe score distribution\n\n"
            f"- Top score: **{scored[0]}/100**\n"
            f"- Top decile: **≥ {scored[len(scored) // 10]}/100**\n"
            f"- Median: {median}/100\n"
            f"- Picks must clear ≥ {min_total_score}/100\n\n"
        )
    else:
        distro = ""

    # Top-momentum names that got low composite (to show where the filter saves you)
    extra: list[str] = []
    sorted_by_mom = sorted(all_candidates, key=lambda x: -x[0].momentum)[:10]
    extra.append("## High-momentum names that scored poorly (filter saves)\n")
    extra.append("| Ticker | Mom 12-1 | F | T | M | A | Total | Why low |")
    extra.append("|---|---:|---:|---:|---:|---:|---:|---|")
    for c, sc in sorted_by_mom:
        if sc["total"] >= min_total_score and c.passed_all:
            continue
        reasons = []
        if not c.passed_all:
            failed = [k for k, v in c.checks.items() if not v]
            reasons.append("filter: " + ",".join(failed))
        else:
            if sc["fundamental"] < 10:
                reasons.append("weak fundamentals")
            if sc["analyst"] < 8:
                reasons.append("weak analyst sentiment")
            if sc["technical"] < 10:
                reasons.append("technical caution")
        extra.append(
            f"| {c.ticker} | {c.momentum * 100:+.1f}% | {sc['fundamental']} | "
            f"{sc['technical']} | {sc['momentum']} | {sc['analyst']} | "
            f"{sc['total']} | {'; '.join(reasons) or '—'} |"
        )
    extra_section = "\n".join(extra) + "\n"

    footer = (
        "\n---\n"
        "*Not investment advice. Composite scoring is a soft ranking on top of the hard quality filters. "
        "It mirrors institutional multi-factor approaches but has NOT been backtested as a unified strategy yet — "
        "treat the composite as a diligence-aid ranking, not a blind execution signal.*\n"
    )
    return header + table + summary + distro + extra_section + footer


def write_report(text: str, reports_dir: Path, slug: str, as_of: date | None = None) -> Path:
    as_of = as_of or date.today()
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"composite_{slug}_{as_of.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    return path
