# trading

Personal algorithmic trading **recommendation** engine for Indian and US equities. Produces ranked daily trade ideas with entry / stop / target / size / conviction / rationale. No broker integration — you execute manually. A paper-book scores how recommendations would have performed.

## Status

v1, single user, paper-only.

## Stack

- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- DuckDB + Parquet for time-series; SQLite for state
- pandas-ta for indicators, vectorbt for backtests
- yfinance + jugaad-data for daily bars
- Anthropic Claude API for news/event LLM agents (later phase)

## Setup

```bash
cd ~/projects/trading
uv sync                                # core deps
uv sync --extra dev                    # + dev tooling
uv sync --extra news --extra backtest  # full feature set
```

## Run

```bash
# Ingest daily bars for the configured universe
uv run trading ingest

# Generate today's pre-open recommendation report
uv run trading report

# Output: reports/YYYY-MM-DD.md
```

## Layout

```
src/trading/
  brokers/      # deferred to v2
  data/         # ingest + feature store
  signals/      # quant signal producers
  agents/       # LLM agents (later phase)
  decision/     # ranker, risk, sizer
  execution/    # paper book simulator (later phase)
  storage/      # duckdb + sqlite wrappers
  backtest/     # vectorbt-based backtests
  monitoring/   # logs, metrics
  config/       # universe, risk limits
  cli.py
```

## Day-1 scope

- yfinance ingest of Nifty 100 + Nifty Next 50 daily bars
- One signal: cross-sectional momentum (12-1 month)
- Markdown pre-open report with ranked ideas

## Out of scope for v1

Brokers, real-time data, intraday triggers, F&O, fully autonomous execution.
