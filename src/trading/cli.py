from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
import pandas as pd

from trading.config.settings import (
    BARS_DUCKDB_PATH,
    DATA_DIR,
    FUNDAMENTALS_DUCKDB_PATH,
    LOGS_DIR,
    REPORTS_DIR,
    STATE_SQLITE_PATH,
    ensure_dirs,
    get_risk_config,
)
from trading.config.universe import get_universe, load_snapshot, snapshot_universe
from trading.data.yfinance_ingest import ingest_ticker, ingest_universe
from trading.decision.recommend import build_recommendations
from trading.reporting.markdown import render, write_report
from trading.storage.bars import BarsStore

UNIVERSES_DIR = DATA_DIR / "universes"


def _resolve_universe(universe: str, snapshot: str = "") -> list[str]:
    """Resolve a ticker list, preferring a frozen snapshot when given."""
    if snapshot:
        return load_snapshot(Path(snapshot))
    return get_universe(universe)


def _build_recs(strategy, bars, risk, top_n, short_n=0, allow_short=False):
    """Build recommendations for the chosen live strategy (shared by `report`
    and `paper-run`)."""
    if strategy == "mean_rev":
        from trading.decision.mean_rev_live import build_mean_rev_recommendations

        return build_mean_rev_recommendations(bars, risk, top_n=top_n, allow_short=allow_short)
    return build_recommendations(bars, risk, top_n=top_n, short_n=short_n)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@click.group()
@click.option("--verbose", is_flag=True, help="Verbose logging")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _setup_logging(verbose)
    ensure_dirs()


@cli.command()
@click.option("--universe", default="nifty50", help="Universe name")
@click.option("--snapshot", default="", help="Frozen-universe snapshot JSON (overrides --universe)")
@click.option("--history-days", default=400, help="History window to ensure exists locally")
@click.option("--full", is_flag=True, help="Force re-fetch of the full window")
@click.option(
    "--source",
    default="yfinance",
    type=click.Choice(["yfinance", "jugaad"]),
    help="yfinance (default, cross-market, adjusted) or jugaad (NSE-direct, unadjusted).",
)
def ingest(universe: str, snapshot: str, history_days: int, full: bool, source: str) -> None:
    """Ingest daily bars for the configured universe."""
    if source == "jugaad":
        from trading.data.jugaad_ingest import ingest_universe as _ingest_universe
    else:
        _ingest_universe = ingest_universe

    tickers = _resolve_universe(universe, snapshot)
    with BarsStore(BARS_DUCKDB_PATH) as store:
        counts = _ingest_universe(store, tickers, history_days=history_days, full=full)
    rows = sum(counts.values())
    ok = sum(1 for v in counts.values() if v > 0)
    fail = sum(1 for v in counts.values() if v == 0)
    click.echo(f"Ingested {rows} rows across {ok} tickers via {source} ({fail} failed/no-update).")


@cli.command()
@click.option("--universe", default="nifty50", help="Universe name")
@click.option("--snapshot", default="", help="Frozen-universe snapshot JSON (overrides --universe)")
@click.option("--top-n", default=10, help="Top N ideas to surface")
@click.option(
    "--strategy",
    default="momentum",
    type=click.Choice(["momentum", "mean_rev"]),
    help="momentum: 12-1 cross-sectional. mean_rev: RSI oversold/overbought reversion.",
)
@click.option("--short-n", default=0, help="momentum: also short the N weakest names")
@click.option("--allow-short", is_flag=True, help="mean_rev: also short overbought bounces")
@click.option(
    "--sizing-mode",
    default="equal_weight",
    type=click.Choice(["equal_weight", "risk_based"]),
    help="equal_weight (default): cap each position at capital/N with a risk ceiling. "
    "risk_based: classic 1%-per-trade sizing (legacy; can leave high-ATR names tiny).",
)
def report(
    universe: str,
    snapshot: str,
    top_n: int,
    strategy: str,
    short_n: int,
    allow_short: bool,
    sizing_mode: str,
) -> None:
    """Generate today's pre-open recommendation report (momentum or mean-reversion)."""
    tickers = _resolve_universe(universe, snapshot)
    risk = get_risk_config().model_copy(update={"sizing_mode": sizing_mode})
    with BarsStore(BARS_DUCKDB_PATH) as store:
        bars = store.load()
    bars = bars[bars["ticker"].isin(tickers)]
    if bars.empty:
        click.echo("No bars in store. Run `trading ingest` first.")
        raise click.Abort()

    recs = _build_recs(strategy, bars, risk, top_n, short_n=short_n, allow_short=allow_short)

    text = render(recs, strategy=strategy)
    path = write_report(text, REPORTS_DIR)
    total_notional = sum(r.notional for r in recs)
    total_risk = sum(r.risk_inr for r in recs)
    n_long = sum(1 for r in recs if r.direction == "LONG")
    n_short = sum(1 for r in recs if r.direction == "SHORT")

    from trading.monitoring import record_event

    record_event(
        "report",
        {
            "strategy": strategy,
            "universe": "snapshot" if snapshot else universe,
            "n_recs": len(recs),
            "n_long": n_long,
            "n_short": n_short,
            "total_notional": round(total_notional, 2),
            "total_risk": round(total_risk, 2),
        },
        LOGS_DIR,
    )
    click.echo(f"Wrote {len(recs)} recommendations ({n_long}L/{n_short}S) to {path}")
    click.echo(
        f"  Total notional: ₹{total_notional:,.0f} "
        f"({total_notional / risk.capital_inr * 100:.1f}% of capital)  "
        f"Total risk: ₹{total_risk:,.0f} ({total_risk / risk.capital_inr * 100:.1f}% of capital)"
    )


@cli.command()
@click.option(
    "--strategy",
    default="momentum",
    type=click.Choice(["momentum", "mean_rev"]),
    help="Strategy to backtest",
)
@click.option("--universe", default="nifty50", help="Universe name")
@click.option("--snapshot", default="", help="Frozen-universe snapshot JSON (overrides --universe)")
@click.option("--top-n", default=10, help="Cross-sectional: # held each rebalance")
@click.option("--max-concurrent", default=10, help="Per-asset: max concurrent positions")
@click.option("--initial-capital", default=100_000.0, help="Starting capital")
@click.option("--cost-bps", default=15.0, help="One-way trading cost (bps), applied to turnover")
@click.option("--benchmark", default="^NSEI", help="Benchmark ticker (empty string to skip)")
@click.option("--rsi-period", default=14, type=int, help="mean_rev: RSI period")
@click.option("--rsi-entry", default=30.0, type=float, help="mean_rev: RSI entry threshold")
@click.option("--rsi-exit", default=60.0, type=float, help="mean_rev: RSI exit threshold")
@click.option("--max-holding-days", default=30, type=int, help="mean_rev: time-stop in days")
@click.option("--label", default="", help="Append a suffix to the output report filename")
def backtest(
    strategy: str,
    universe: str,
    snapshot: str,
    top_n: int,
    max_concurrent: int,
    initial_capital: float,
    cost_bps: float,
    benchmark: str,
    rsi_period: int,
    rsi_entry: float,
    rsi_exit: float,
    max_holding_days: int,
    label: str,
) -> None:
    """Run a historical backtest of the given strategy."""
    from trading.backtest import mean_rev_bt, momentum_bt
    from trading.backtest.metrics import annual_breakdown, compute_metrics
    from trading.backtest.report import render as render_bt
    from trading.backtest.report import write_report as write_bt

    tickers = _resolve_universe(universe, snapshot)
    with BarsStore(BARS_DUCKDB_PATH) as store:
        if benchmark:
            ingest_ticker(store, benchmark, history_days=2200)
        bars = store.load()

    strat_bars = bars[bars["ticker"].isin(tickers)]
    if strat_bars.empty:
        click.echo("No bars in store. Run `trading ingest` first.")
        raise click.Abort()

    if strategy == "momentum":
        result = momentum_bt.run(
            strat_bars, top_n=top_n, initial_capital=initial_capital, cost_bps=cost_bps
        )
    elif strategy == "mean_rev":
        result = mean_rev_bt.run(
            strat_bars,
            max_concurrent=max_concurrent,
            initial_capital=initial_capital,
            cost_bps=cost_bps,
            rsi_period=rsi_period,
            rsi_entry=rsi_entry,
            rsi_exit=rsi_exit,
            max_holding_days=max_holding_days,
        )
    else:
        raise click.ClickException(f"Unknown strategy: {strategy}")

    gross_metrics = compute_metrics(result.gross_returns)
    net_metrics = compute_metrics(result.returns)
    annual_net = annual_breakdown(result.returns)

    bench_metrics = None
    annual_bench = None
    if benchmark and not result.returns.empty:
        b = bars[bars["ticker"] == benchmark].sort_values("date")
        if not b.empty:
            b = b.set_index(pd.to_datetime(b["date"]))
            b_ret = b["adj_close"].pct_change(fill_method=None).dropna()
            b_ret = b_ret.loc[result.returns.index.min() : result.returns.index.max()]
            bench_metrics = compute_metrics(b_ret)
            annual_bench = annual_breakdown(b_ret)

    if result.rebalance_dates:
        n_rebals = max(1, len(result.rebalance_dates))
        avg_turnover = float(result.turnover.sum()) / n_rebals
    else:
        avg_turnover = 0.0
    total_cost = float(result.costs.sum())

    config = {
        "strategy": strategy,
        "universe": universe,
        "initial_capital": initial_capital,
        "cost_bps_per_side": cost_bps,
        "benchmark": benchmark or "—",
        "period": (
            f"{result.returns.index.min().date()} → {result.returns.index.max().date()}"
            if not result.returns.empty
            else "—"
        ),
    }
    if strategy == "momentum":
        config.update(
            {
                "top_n": top_n,
                "rebalance": "monthly",
                "n_rebalances": len(result.rebalance_dates or []),
            }
        )
    elif strategy == "mean_rev":
        n_trades = 0 if result.trades is None else len(result.trades)
        config.update(
            {
                "max_concurrent": max_concurrent,
                "rebalance": "signal-driven",
                "rsi_period": rsi_period,
                "rsi_entry": rsi_entry,
                "rsi_exit": rsi_exit,
                "max_holding_days": max_holding_days,
                "n_trades": n_trades,
            }
        )

    text = render_bt(
        strategy=strategy,
        gross=gross_metrics,
        net=net_metrics,
        benchmark=bench_metrics,
        config=config,
        annual_net=annual_net,
        annual_benchmark=annual_bench,
        avg_turnover=avg_turnover,
        total_cost=total_cost,
        trades=result.trades,
    )
    slug = f"{strategy}_{label}" if label else strategy
    path = write_bt(text, REPORTS_DIR, slug=slug)
    click.echo(f"Wrote backtest report to {path}")
    click.echo(
        f"  Gross    : CAGR {gross_metrics.cagr * 100:6.2f}%  "
        f"Sharpe {gross_metrics.sharpe:5.2f}  "
        f"MDD {gross_metrics.max_drawdown * 100:6.2f}%"
    )
    click.echo(
        f"  Net      : CAGR {net_metrics.cagr * 100:6.2f}%  "
        f"Sharpe {net_metrics.sharpe:5.2f}  "
        f"MDD {net_metrics.max_drawdown * 100:6.2f}%  "
        f"WinRate {net_metrics.monthly_win_rate * 100:5.1f}%"
    )
    if bench_metrics is not None:
        click.echo(
            f"  Benchmark: CAGR {bench_metrics.cagr * 100:6.2f}%  "
            f"Sharpe {bench_metrics.sharpe:5.2f}  "
            f"MDD {bench_metrics.max_drawdown * 100:6.2f}%"
        )
    click.echo(
        f"  Avg turnover/rebal: {avg_turnover * 100:.1f}%   "
        f"Total cost drag: {total_cost * 100:.2f}%"
    )


@cli.command()
@click.option("--universe", default="nifty100", help="Universe name")
@click.option("--top-n", default=15, help="Top N watchlist entries")
@click.option("--reward-atr", default=1.5, type=float, help="Target as ATR multiple beyond trigger")
@click.option(
    "--min-vol-ratio",
    default=1.5,
    type=float,
    help="Filter: setup-day volume / 20d avg volume. Backtest sweet spot is 1.5–2.0.",
)
def intraday(universe: str, top_n: int, reward_atr: float, min_vol_ratio: float) -> None:
    """Generate tomorrow's intraday watchlist (NR7 / Inside Day compression setups)."""
    from trading.decision.intraday import build_intraday_watchlist
    from trading.reporting.intraday_markdown import render as render_intra
    from trading.reporting.intraday_markdown import write_report as write_intra

    tickers = get_universe(universe)
    risk = get_risk_config()
    with BarsStore(BARS_DUCKDB_PATH) as store:
        bars = store.load()
    bars = bars[bars["ticker"].isin(tickers)]
    if bars.empty:
        click.echo("No bars in store. Run `trading ingest` first.")
        raise click.Abort()
    ideas = build_intraday_watchlist(
        bars,
        risk,
        top_n=top_n,
        reward_atr_multiple=reward_atr,
        min_volume_ratio=min_vol_ratio,
    )
    text = render_intra(ideas)
    path = write_intra(text, REPORTS_DIR)
    click.echo(f"Wrote {len(ideas)} intraday setups to {path}")


@cli.command("quality-report")
@click.option("--universe", default="nifty100", help="Universe name")
@click.option("--top-n", default=10, help="Top N picks after filtering")
@click.option("--max-per-sector", default=3, help="Max names per sector")
@click.option("--max-age-days", default=7, help="Cache TTL for fundamentals")
@click.option("--refresh-fundamentals", is_flag=True, help="Force re-fetch fundamentals")
def quality_report(
    universe: str,
    top_n: int,
    max_per_sector: int,
    max_age_days: int,
    refresh_fundamentals: bool,
) -> None:
    """Generate quality-filtered recommendations (technical + fundamental)."""
    from trading.data.fundamentals import fetch_universe
    from trading.decision.quality import quality_picks
    from trading.reporting.quality_markdown import render as render_q
    from trading.reporting.quality_markdown import write_report as write_q
    from trading.storage.fundamentals import FundamentalsStore

    tickers = get_universe(universe)

    with FundamentalsStore(FUNDAMENTALS_DUCKDB_PATH) as fs:
        click.echo(f"Fetching fundamentals for {len(tickers)} tickers (cache TTL {max_age_days}d)…")
        results = fetch_universe(
            tickers, fs, max_age_days=0 if refresh_fundamentals else max_age_days
        )
        cached = sum(1 for v in results.values() if v == "cached")
        fetched = sum(1 for v in results.values() if v == "fetched")
        errors = sum(1 for v in results.values() if v == "error")
        click.echo(f"  cached={cached}  fetched={fetched}  errors={errors}")

        with BarsStore(BARS_DUCKDB_PATH) as bs:
            bars = bs.load()
        bars = bars[bars["ticker"].isin(tickers)]

        picks, all_cands = quality_picks(bars, fs, top_n=top_n, max_per_sector=max_per_sector)

    text = render_q(picks, all_cands, universe=universe, max_per_sector=max_per_sector)
    path = write_q(text, REPORTS_DIR, slug=universe)
    click.echo(
        f"Wrote {len(picks)} quality picks "
        f"(from {sum(1 for c in all_cands if c.passed_all)} passing of {len(all_cands)} evaluable) "
        f"to {path}"
    )
    for p in picks:
        click.echo(
            f"  {p.ticker:18s} mom={p.momentum * 100:+6.1f}%  "
            f"P/E={(p.forward_pe or 0):>5.1f}  RSI={p.rsi:>4.0f}  "
            f"ext={p.extension_pct * 100:>+5.1f}%  sector={p.sector or '—'}"
        )


@cli.command("composite-report")
@click.option("--universe", default="sp100", help="Universe name")
@click.option("--top-n", default=10, help="Top N picks after composite ranking")
@click.option("--max-per-sector", default=3, help="Max names per sector")
@click.option("--min-total-score", default=50, help="Minimum composite score (0-100)")
@click.option("--max-age-days", default=7, help="Cache TTL for fundamentals")
@click.option("--refresh-fundamentals", is_flag=True, help="Force re-fetch fundamentals")
def composite_report(
    universe: str,
    top_n: int,
    max_per_sector: int,
    min_total_score: int,
    max_age_days: int,
    refresh_fundamentals: bool,
) -> None:
    """Multi-factor composite ranking (fundamental + technical + momentum + analyst)."""
    from trading.data.fundamentals import fetch_universe
    from trading.decision.quality import composite_picks
    from trading.reporting.composite_markdown import render as render_c
    from trading.reporting.composite_markdown import write_report as write_c
    from trading.storage.fundamentals import FundamentalsStore

    tickers = get_universe(universe)

    with FundamentalsStore(FUNDAMENTALS_DUCKDB_PATH) as fs:
        click.echo(f"Ensuring fundamentals for {len(tickers)} tickers (cache TTL {max_age_days}d)…")
        results = fetch_universe(
            tickers, fs, max_age_days=0 if refresh_fundamentals else max_age_days
        )
        cached = sum(1 for v in results.values() if v == "cached")
        fetched = sum(1 for v in results.values() if v == "fetched")
        errors = sum(1 for v in results.values() if v == "error")
        click.echo(f"  cached={cached}  fetched={fetched}  errors={errors}")

        with BarsStore(BARS_DUCKDB_PATH) as bs:
            bars = bs.load()
        bars = bars[bars["ticker"].isin(tickers)]

        picks, all_cands = composite_picks(
            bars, fs,
            top_n=top_n, max_per_sector=max_per_sector, min_total_score=min_total_score,
        )

    text = render_c(
        picks, all_cands,
        universe=universe, max_per_sector=max_per_sector, min_total_score=min_total_score,
    )
    path = write_c(text, REPORTS_DIR, slug=universe)
    click.echo(f"Wrote {len(picks)} composite picks to {path}")
    for c, sc in picks:
        click.echo(
            f"  {c.ticker:8s} F={sc['fundamental']:>2d} T={sc['technical']:>2d} "
            f"M={sc['momentum']:>2d} A={sc['analyst']:>2d}  TOTAL={sc['total']:>3d}  "
            f"({c.sector})"
        )


@cli.command("universe-snapshot")
@click.option("--universe", default="nifty50", help="Universe name to freeze")
def universe_snapshot(universe: str) -> None:
    """Freeze a universe's current constituents to a dated JSON snapshot.

    Backtests/reports can then pass `--snapshot <path>` for a reproducible,
    membership-dated run. NOTE: this captures *today's* index members, so it
    does not remove survivorship bias — it only makes the bias explicit and the
    run reproducible. See trading.config.universe for the full caveat.
    """
    path = snapshot_universe(universe, UNIVERSES_DIR)
    tickers = load_snapshot(path)
    click.echo(f"Snapshot of {universe} ({len(tickers)} tickers) → {path}")
    click.echo("  Survivorship caveat: these are *current* members; not point-in-time.")


@cli.command("paper-run")
@click.option("--universe", default="nifty50", help="Universe name")
@click.option("--snapshot", default="", help="Frozen-universe snapshot JSON (overrides --universe)")
@click.option("--strategy", default="momentum", type=click.Choice(["momentum", "mean_rev"]))
@click.option("--top-n", default=10, help="Top N ideas to open")
@click.option("--short-n", default=0, help="momentum: also short the N weakest names")
@click.option("--allow-short", is_flag=True, help="mean_rev: also short overbought bounces")
@click.option("--cost-bps-per-side", default=7.5, type=float, help="Paper broker cost (bps/side)")
@click.option("--slippage-bps", default=0.0, type=float, help="Adverse slippage per fill (bps)")
def paper_run(
    universe: str,
    snapshot: str,
    strategy: str,
    top_n: int,
    short_n: int,
    allow_short: bool,
    cost_bps_per_side: float,
    slippage_bps: float,
) -> None:
    """Open today's recommendations as tracked paper positions (no real money)."""
    from trading.brokers import BpsFeeModel, PaperBroker
    from trading.execution import PaperBook
    from trading.storage.state import StateStore

    tickers = _resolve_universe(universe, snapshot)
    risk = get_risk_config()
    with BarsStore(BARS_DUCKDB_PATH) as store:
        bars = store.load()
    bars = bars[bars["ticker"].isin(tickers)]
    if bars.empty:
        click.echo("No bars in store. Run `trading ingest` first.")
        raise click.Abort()

    recs = _build_recs(strategy, bars, risk, top_n, short_n=short_n, allow_short=allow_short)
    if not recs:
        click.echo("No recommendations to open.")
        return

    broker = PaperBroker(BpsFeeModel(bps_per_side=cost_bps_per_side), slippage_bps=slippage_bps)
    with StateStore(STATE_SQLITE_PATH) as state:
        pos_ids = PaperBook(state, broker).open(recs, strategy)
    click.echo(f"Opened {len(pos_ids)} paper positions ({strategy}) in {STATE_SQLITE_PATH}")


@cli.command("paper-update")
@click.option("--universe", default="nifty100", help="Universe scope for bar lookups")
@click.option("--snapshot", default="", help="Frozen-universe snapshot JSON (overrides --universe)")
@click.option("--max-holding-days", default=60, type=int, help="Time-stop for open positions")
@click.option("--cost-bps-per-side", default=7.5, type=float, help="Paper broker cost (bps/side)")
def paper_update(
    universe: str, snapshot: str, max_holding_days: int, cost_bps_per_side: float
) -> None:
    """Close open paper positions that have hit a stop / target / time-stop."""
    from trading.brokers import BpsFeeModel, PaperBroker
    from trading.execution import PaperBook
    from trading.storage.state import StateStore

    tickers = _resolve_universe(universe, snapshot)
    with BarsStore(BARS_DUCKDB_PATH) as store:
        bars = store.load()
    bars = bars[bars["ticker"].isin(tickers)]

    broker = PaperBroker(BpsFeeModel(bps_per_side=cost_bps_per_side))
    with StateStore(STATE_SQLITE_PATH) as state:
        book = PaperBook(state, broker)
        reasons = book.update(bars, max_holding_days=max_holding_days)
        s = book.summary(bars)
    closed = sum(reasons.values())
    detail = ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())) or "none"
    click.echo(f"Closed {closed} position(s): {detail}")
    click.echo(
        f"  Open {s.open_count} | Closed {s.closed_count} | "
        f"Win rate {s.win_rate * 100:.0f}%"
    )


@cli.command("paper-status")
@click.option("--universe", default="nifty100", help="Universe scope for mark-to-market")
@click.option("--snapshot", default="", help="Frozen-universe snapshot JSON (overrides --universe)")
def paper_status(universe: str, snapshot: str) -> None:
    """Show the paper book: open positions, realized + unrealized P&L, fees."""
    from trading.execution import summarize
    from trading.storage.state import StateStore

    tickers = _resolve_universe(universe, snapshot)
    with BarsStore(BARS_DUCKDB_PATH) as store:
        bars = store.load()
    bars = bars[bars["ticker"].isin(tickers)]

    with StateStore(STATE_SQLITE_PATH) as state:
        s = summarize(state, bars if not bars.empty else None)
        open_pos = state.get_positions("open")

    click.echo(f"Paper book @ {STATE_SQLITE_PATH}")
    click.echo(
        f"  Open: {s.open_count}   Closed: {s.closed_count}   "
        f"Win rate: {s.win_rate * 100:.0f}%"
    )
    click.echo(
        f"  Realized P&L: ₹{s.realized_pnl:,.0f}   "
        f"Unrealized: ₹{s.unrealized_pnl:,.0f}   Fees: ₹{s.total_fees:,.0f}"
    )
    for _, p in open_pos.iterrows():
        click.echo(
            f"    {p['ticker']:14s} {p['direction']:5s} x{int(p['qty']):<4d} "
            f"@ {p['entry_price']:.2f}  stop {p['stop']:.2f}  target {p['target']:.2f}"
        )


@cli.command()
@click.argument("ticker")
@click.option("--limit", default=8, help="Max headlines to fetch")
@click.option("--region", default="IN", help="News region (IN, US, …)")
@click.option("--assess", is_flag=True, help="Run the Claude news agent for a sentiment read")
@click.option("--model", default="", help="Override the LLM model id")
def news(ticker: str, limit: int, region: str, assess: bool, model: str) -> None:
    """Fetch recent headlines for a ticker (and optionally an LLM sentiment read).

    Needs the 'news' extra: `uv sync --extra news`. The LLM read also needs
    ANTHROPIC_API_KEY. Both degrade with a clear message if unavailable.
    """
    from trading.agents import assess_ticker, fetch_headlines
    from trading.agents.sentiment import DEFAULT_MODEL

    try:
        headlines = fetch_headlines(ticker, limit=limit, region=region)
    except RuntimeError as exc:
        click.echo(str(exc))
        raise click.Abort() from exc

    click.echo(f"{len(headlines)} headline(s) for {ticker}:")
    for i, h in enumerate(headlines, 1):
        src = f"  [{h.source}]" if h.source else ""
        click.echo(f"  {i}. {h.title}{src}")

    if assess:
        try:
            a = assess_ticker(ticker, headlines, model=model or DEFAULT_MODEL)
        except RuntimeError as exc:
            click.echo(f"\nLLM assessment unavailable: {exc}")
            return
        click.echo(
            f"\nAssessment: {a.sentiment.upper()} "
            f"(score {a.score:+.2f}, confidence {a.confidence:.0%})"
        )
        click.echo(f"  {a.summary}")
        if a.events:
            click.echo("  Events: " + "; ".join(a.events))


@cli.command()
@click.argument("tickers", nargs=-1)
def quote(tickers: tuple[str, ...]) -> None:
    """Fetch delayed real-time last prices for one or more tickers."""
    if not tickers:
        click.echo("Provide one or more tickers, e.g. `trading quote RELIANCE.NS TCS.NS`.")
        return
    from trading.data.realtime import get_quotes

    for t, q in get_quotes(list(tickers)).items():
        if q.price is None:
            click.echo(f"  {t:14s} — no quote")
            continue
        chg = f"{q.change_pct * 100:+.2f}%" if q.change_pct is not None else "—"
        cur = q.currency or ""
        click.echo(f"  {t:14s} {q.price:>10.2f} {cur:<4s} {chg:>8s}")


@cli.command()
@click.option("--name", default="", help="Filter to one event type (e.g. report)")
@click.option("--limit", default=20, help="Show the last N events")
def metrics(name: str, limit: int) -> None:
    """Show recent run-metrics events from logs/metrics.jsonl."""
    from trading.monitoring import read_events

    df = read_events(LOGS_DIR, name or None)
    if df.empty:
        click.echo("No metrics recorded yet.")
        return
    for _, row in df.tail(limit).iterrows():
        fields = {k: v for k, v in row.items() if k not in ("ts", "event")}
        kv = "  ".join(f"{k}={v}" for k, v in fields.items())
        click.echo(f"{row['ts']}  {row['event']:12s}  {kv}")


@cli.command()
@click.option("--port", default=8501, help="Port to serve on")
@click.option("--no-browser", is_flag=True, help="Do not auto-open a browser")
def web(port: int, no_browser: bool) -> None:
    """Launch the Streamlit dashboard (needs the web extra: `uv sync --extra web`)."""
    try:
        from streamlit.web import cli as stcli
    except ImportError as exc:
        raise click.ClickException(
            "Streamlit is not installed. Run: uv sync --extra web"
        ) from exc

    app_path = Path(__file__).parent / "web" / "app.py"
    argv = ["streamlit", "run", str(app_path), "--server.port", str(port)]
    if no_browser:
        argv += ["--server.headless", "true"]
    sys.argv = argv
    click.echo(f"Starting dashboard at http://localhost:{port} …")
    stcli.main()


def main() -> None:
    # Reports are INR-denominated and echo the ₹ glyph; the default Windows
    # console codepage (cp1252) can't encode it. Force UTF-8 on our own streams.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # pragma: no cover - stream-dependent
            pass
    cli(obj={})


if __name__ == "__main__":
    main()
