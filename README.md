# trading

Personal algorithmic trading **recommendation** engine for Indian and US equities. Produces ranked daily trade ideas with entry / stop / target / size / conviction / rationale. No live broker routing — you execute manually (or against the built-in paper broker). A paper-book scores how recommendations would have performed.

## Status

v1, single user, paper-only. Long **and** short. Two live strategies (momentum, mean-reversion), a paper-trading book, optional LLM news agents, and a backtester.

## Stack

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- DuckDB for time-series (price bars, fundamentals); SQLite for paper-book state
- pandas / numpy for the math, pandas-ta for indicators
- Custom backtesters (vectorised cross-sectional + event-driven per-asset) — no vectorbt
- yfinance (cross-market, adjusted) or jugaad-data (NSE-direct) for daily bars
- yfinance `fast_info` for delayed real-time quotes
- Anthropic Claude API for the optional news/event LLM agents (`news` extra)

## Setup

```bash
cd ~/projects/trading
uv sync                 # core deps (ingest, signals, decision, backtest, paper book)
uv sync --extra dev     # + pytest, ruff
uv sync --extra news    # + feedparser, anthropic (LLM news/event agents)
uv sync --extra web     # + streamlit (the dashboard)
```

## Dashboard

A Streamlit web UI that shows and configures everything — universe & risk in the
sidebar, plus pages for recommendations (momentum / mean-rev, long & short),
intraday setups, quality/composite picks, backtests (metrics + equity/annual
charts), the paper book (open/update/status), news + LLM sentiment, delayed
quotes, and a Config page (ingest, fundamentals refresh, universe snapshots,
run-metrics log).

```bash
uv sync --extra web
uv run trading web                 # opens http://localhost:8501
uv run trading web --port 8600 --no-browser
```

## Run

```bash
# Ingest daily bars (yfinance by default; --source jugaad for NSE-direct)
uv run trading ingest --universe nifty50
uv run trading ingest --universe nifty50 --source jugaad

# Pre-open recommendation report (momentum long-only by default)
uv run trading report                              # → reports/YYYY-MM-DD.md
uv run trading report --top-n 5 --short-n 2        # long leaders + short laggards
uv run trading report --strategy mean_rev --allow-short

# Paper-trading book (no real money; state in data/state.sqlite)
uv run trading paper-run --top-n 5 --short-n 2     # open today's ideas as positions
uv run trading paper-update                        # close on stop / target / time-stop
uv run trading paper-status                        # open positions + realized/unrealized P&L

# Other reports
uv run trading intraday                            # NR7 / Inside-Day next-day watchlist
uv run trading quality-report --universe nifty100  # technical + fundamental filter
uv run trading composite-report --universe sp100   # 4-factor composite ranking

# Backtests (momentum or mean_rev), net of costs vs a benchmark
uv run trading backtest --strategy momentum --benchmark ^NSEI
uv run trading backtest --strategy mean_rev --rsi-entry 30 --rsi-exit 60

# News agent (needs --extra news + ANTHROPIC_API_KEY); degrades gracefully
uv run trading news RELIANCE.NS --assess

# Misc
uv run trading quote RELIANCE.NS TCS.NS            # delayed real-time quotes
uv run trading metrics                             # recent run-metrics log
uv run trading universe-snapshot --universe nifty50  # freeze constituents (see below)
```

## Layout

```
src/trading/
  config/       # universe lists + snapshots, risk limits, paths
  data/         # ingest (yfinance / jugaad) + fundamentals + realtime quotes
  storage/      # duckdb (bars, fundamentals) + sqlite (paper-book state)
  signals/      # quant signal producers (momentum, mean-reversion, compression)
  decision/     # rankers, risk, sizing (momentum, mean-rev-live, quality, composite, intraday)
  reporting/    # markdown report renderers
  backtest/     # cross-sectional + per-asset backtesters, metrics, reports
  brokers/      # Broker interface + PaperBroker (+ Kite stub)
  execution/    # paper-book simulator (opens/marks/closes positions)
  agents/       # LLM news/event agents (optional: feedparser + anthropic)
  monitoring/   # structured run-metrics log
  web/          # Streamlit dashboard (app.py entry, views.py pages, lib.py helpers)
  cli.py
```

## Long / short

The momentum recommender goes long the strongest names and (with `--short-n`) shorts the weakest *negative-momentum* names. The mean-reversion recommender goes long oversold pullbacks in uptrends and (with `--allow-short`) shorts overbought bounces in downtrends. Shorts get mirrored stops (above entry) and targets (below entry); sizing is identical to longs (keyed off the ATR stop distance).

## Survivorship bias

The universe lists are the *current* index members, so historical backtests are survivorship-biased (dropped names absent; current names present for the whole window). There is no free point-in-time NSE/S&P constituent feed bundled here, so this is **documented, not eliminated**.

What is provided is reproducibility: `trading universe-snapshot` freezes today's constituents to a dated JSON, and `report`/`backtest`/`ingest --snapshot <path>` replay exactly that set. When a true point-in-time feed is wired in later, snapshots stay the loading mechanism and only the constituent source changes.

## Testing

```bash
uv run pytest          # unit + end-to-end CLI tests on synthetic data
uv run ruff check src tests
```

## Out of scope for v1

Live broker order routing (a `KiteBroker` interface stub exists but raises `NotImplementedError`), streaming real-time data, F&O, and fully autonomous execution. The paper broker, delayed quotes, and the paper-book are in.

---
*Not investment advice. Paper-only research tooling.*
