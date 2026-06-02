from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from textwrap import dedent

from trading.decision.intraday import IntradayIdea


def render(ideas: list[IntradayIdea], as_of: date | None = None) -> str:
    as_of = as_of or date.today()
    next_session = as_of + timedelta(days=1)

    if not ideas:
        return (
            f"# Intraday watchlist — for {next_session.isoformat()}\n\n"
            f"No compression setups found as of {as_of.isoformat()}.\n"
        )

    header = dedent(
        f"""\
        # Intraday watchlist — for {next_session.isoformat()}

        Compression setups detected on {as_of.isoformat()} bars. Trade tomorrow,
        exit by 3:15 PM IST. Paper-trade only — verify before any execution.

        | # | Ticker | Setup | Ref close | **Long ≥** | Stop | Target | Shares | **Short ≤** | Stop | Target | ATR/Range |
        |---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
        """
    )
    rows = []
    for i, x in enumerate(ideas, start=1):
        rows.append(
            f"| {i} | {x.ticker} | {x.setup} | {x.ref_close:.2f} | "
            f"**{x.breakout:.2f}** | {x.long_stop:.2f} | {x.long_target:.2f} | {x.long_shares} | "
            f"**{x.breakdown:.2f}** | {x.short_stop:.2f} | {x.short_target:.2f} | "
            f"{x.compression:.2f}× |"
        )
    table = header + "\n".join(rows) + "\n"

    notes = dedent(
        """

        ## How to use (rules backed by sweep on 2020–2026 Nifty 100)

        - **Filter applied**: volume on the setup day ≥ 1.5× the 20-day average. Without this filter
          the edge disappears.
        - **Inside Day setups outperformed NR7-only** in backtest (+0.16% vs +0.00% net per trade);
          they appear first in the table.
        - **Exit at the close, not on a stop.** Backtest showed that "stop at today's low" is too tight
          and turns winners into losers. Better expectancy without the stop.
        - **Trade in size you can afford to lose at close**: avg P&L is +0.17% net per trade, win rate ≈ 51%.
          This is a small, marginal edge — not a high-conviction signal.
        - **Compression ratio** (ATR / today's range) — higher = tighter coil. Shown for reference.
        - **Trend filter (close > SMA200) was tested and did not help**, so it's not applied.

        Long/short trigger levels and stop/target columns are shown for reference if you do want to
        place mechanical stops, but the backtested expectancy is for the close-out variant.

        ---
        *Not investment advice. Pre-market scan based on daily compression patterns (NR7 / Inside Day)
        with volume confirmation. v1 — no intraday/real-time confirmation.*
        """
    )
    return table + notes


def write_report(text: str, reports_dir: Path, as_of: date | None = None) -> Path:
    as_of = as_of or date.today()
    reports_dir.mkdir(parents=True, exist_ok=True)
    next_session = as_of + timedelta(days=1)
    path = reports_dir / f"intraday_{next_session.isoformat()}.md"
    path.write_text(text, encoding="utf-8")
    return path
