"""Page renderers for the Streamlit dashboard. Each function draws one page and
reads global config from session state (see lib.risk_config / current_tickers)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from trading.config.settings import LOGS_DIR, STATE_SQLITE_PATH
from trading.web import lib


def _need_bars(tickers):
    bars = lib.load_bars(tickers)
    if bars.empty:
        st.warning(
            "No bars in the store for this universe. Go to **Config → Ingest** "
            "to download data first."
        )
        return None
    return bars


# ---- Dashboard ----------------------------------------------------------


def dashboard() -> None:
    st.header("📊 Dashboard")
    status = lib.data_status()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tickers in store", status["tickers"])
    c2.metric("Bar rows", f"{status['rows']:,}")
    c3.metric("History start", str(status["start"] or "—"))
    c4.metric("Latest bar", str(status["end"] or "—"))

    st.caption(f"Active universe: **{lib.universe_label()}**  ·  Fundamentals cached: "
               f"{lib.fundamentals_count()} tickers")

    st.subheader("Paper book")
    if lib.has_state_db():
        from trading.execution import summarize
        from trading.storage.state import StateStore

        bars = lib.load_bars(lib.current_tickers())
        with StateStore(STATE_SQLITE_PATH) as state:
            s = summarize(state, bars if not bars.empty else None)
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Open", s.open_count)
        d2.metric("Closed", s.closed_count)
        d3.metric("Realized P&L ₹", f"{s.realized_pnl:,.0f}")
        d4.metric("Unrealized ₹", f"{s.unrealized_pnl:,.0f}")
    else:
        st.info("No paper book yet. Open positions from the **Paper Book** page.")

    st.subheader("Recent runs")
    m = lib.recent_metrics()
    if m.empty:
        st.caption("No runs recorded yet.")
    else:
        st.dataframe(m, hide_index=True, width="stretch")


# ---- Ideas --------------------------------------------------------------


def ideas() -> None:
    st.header("💡 Recommendations")
    tickers = lib.current_tickers()
    bars = _need_bars(tickers)
    if bars is None:
        return

    c1, c2, c3 = st.columns(3)
    strategy = c1.selectbox("Strategy", ["momentum", "mean_rev"], key="ideas_strat_sel")
    top_n = int(c2.number_input("Top N", 1, 50, 10, key="ideas_topn"))
    if strategy == "momentum":
        short_n = int(c3.number_input("Short N (laggards)", 0, 20, 0, key="ideas_shortn"))
        allow_short = False
    else:
        allow_short = c3.checkbox("Allow shorts", value=False, key="ideas_allowshort")
        short_n = 0

    if st.button("Generate ideas", type="primary"):
        risk = lib.risk_config()
        if strategy == "mean_rev":
            from trading.decision.mean_rev_live import build_mean_rev_recommendations

            recs = build_mean_rev_recommendations(
                bars, risk, top_n=top_n, allow_short=allow_short
            )
        else:
            from trading.decision.recommend import build_recommendations

            recs = build_recommendations(bars, risk, top_n=top_n, short_n=short_n)
        st.session_state["ideas_recs"] = recs
        st.session_state["ideas_strategy"] = strategy

    recs = st.session_state.get("ideas_recs")
    if recs is None:
        st.caption("Set parameters and click **Generate ideas**.")
        return
    if not recs:
        st.info("No recommendations matched the filters.")
        return

    risk = lib.risk_config()
    df = lib.recs_to_df(recs)
    st.dataframe(df, hide_index=True, width="stretch")

    notional = sum(r.notional for r in recs)
    risk_inr = sum(r.risk_inr for r in recs)
    n_long = sum(1 for r in recs if r.direction == "LONG")
    n_short = sum(1 for r in recs if r.direction == "SHORT")
    a, b, c = st.columns(3)
    a.metric("Long / Short", f"{n_long} / {n_short}")
    b.metric("Notional", f"₹{notional:,.0f}", f"{notional / risk.capital_inr * 100:.1f}% of cap")
    c.metric("Risk", f"₹{risk_inr:,.0f}", f"{risk_inr / risk.capital_inr * 100:.1f}% of cap")

    from trading.reporting.markdown import render

    strat = st.session_state.get("ideas_strategy", "momentum")
    md = render(recs, strategy=strat)
    e1, e2 = st.columns(2)
    e1.download_button("⬇ Download report (.md)", md, file_name="recommendations.md")
    if e2.button("📓 Open these in the paper book"):
        from trading.brokers import PaperBroker
        from trading.execution import PaperBook
        from trading.storage.state import StateStore

        with StateStore(STATE_SQLITE_PATH) as state:
            ids = PaperBook(state, PaperBroker()).open(recs, strat)
        st.success(f"Opened {len(ids)} paper positions.")


# ---- Intraday -----------------------------------------------------------


def intraday() -> None:
    st.header("⚡ Intraday watchlist (NR7 / Inside-Day)")
    tickers = lib.current_tickers()
    bars = _need_bars(tickers)
    if bars is None:
        return

    c1, c2, c3 = st.columns(3)
    top_n = int(c1.number_input("Top N", 1, 50, 15))
    reward_atr = float(c2.number_input("Reward (× ATR)", 0.5, 5.0, 1.5, step=0.1))
    min_vol = float(c3.number_input("Min volume ratio", 0.5, 5.0, 1.5, step=0.1))

    if st.button("Scan setups", type="primary"):
        from trading.decision.intraday import build_intraday_watchlist

        ideas_ = build_intraday_watchlist(
            bars, lib.risk_config(), top_n=top_n,
            reward_atr_multiple=reward_atr, min_volume_ratio=min_vol,
        )
        st.session_state["intraday_ideas"] = ideas_

    ideas_ = st.session_state.get("intraday_ideas")
    if ideas_ is None:
        return
    if not ideas_:
        st.info("No compression setups found.")
        return
    rows = [
        {
            "Ticker": x.ticker, "Setup": x.setup, "Ref close": round(x.ref_close, 2),
            "Long ≥": round(x.breakout, 2), "L stop": round(x.long_stop, 2),
            "L target": round(x.long_target, 2), "Short ≤": round(x.breakdown, 2),
            "ATR/Range": round(x.compression, 2),
        }
        for x in ideas_
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---- Quality / Composite ------------------------------------------------


def quality() -> None:
    st.header("🔎 Quality & Composite picks")
    tickers = lib.current_tickers()
    bars = _need_bars(tickers)
    if bars is None:
        return

    n_fund = lib.fundamentals_count()
    st.caption(f"Fundamentals cached: {n_fund} tickers.")
    if n_fund == 0:
        st.warning("No fundamentals cached. Fetch them below (network call).")
    with st.expander("Fetch / refresh fundamentals (network)"):
        max_age = int(st.number_input("Cache TTL (days)", 0, 90, 7))
        if st.button("Fetch fundamentals now"):
            from trading.config.settings import FUNDAMENTALS_DUCKDB_PATH
            from trading.data.fundamentals import fetch_universe
            from trading.storage.fundamentals import FundamentalsStore

            with st.spinner(f"Fetching fundamentals for {len(tickers)} tickers…"):
                with FundamentalsStore(FUNDAMENTALS_DUCKDB_PATH) as fs:
                    res = fetch_universe(tickers, fs, max_age_days=max_age)
            ok = sum(1 for v in res.values() if v in ("fetched", "cached"))
            st.success(f"Done: {ok}/{len(tickers)} have fundamentals.")

    mode = st.radio("Ranking", ["quality (momentum-ranked)", "composite (4-factor)"],
                    horizontal=True)
    c1, c2, c3 = st.columns(3)
    top_n = int(c1.number_input("Top N", 1, 50, 10, key="q_topn"))
    max_sec = int(c2.number_input("Max per sector", 1, 10, 3, key="q_sec"))
    min_score = int(c3.number_input("Min composite score", 0, 100, 50, key="q_min"))

    if st.button("Run", type="primary"):
        from trading.config.settings import FUNDAMENTALS_DUCKDB_PATH
        from trading.decision.quality import composite_picks, quality_picks
        from trading.storage.fundamentals import FundamentalsStore

        with FundamentalsStore(FUNDAMENTALS_DUCKDB_PATH) as fs:
            if mode.startswith("composite"):
                picks, _ = composite_picks(bars, fs, top_n=top_n,
                                           max_per_sector=max_sec, min_total_score=min_score)
                rows = [
                    {"Ticker": c.ticker, "Sector": c.sector, "Total": sc["total"],
                     "F": sc["fundamental"], "T": sc["technical"], "M": sc["momentum"],
                     "A": sc["analyst"], "P/E": c.forward_pe, "RSI": round(c.rsi, 0)}
                    for c, sc in picks
                ]
            else:
                picks, _ = quality_picks(bars, fs, top_n=top_n, max_per_sector=max_sec)
                rows = [
                    {"Ticker": c.ticker, "Sector": c.sector,
                     "Momentum %": round(c.momentum * 100, 1), "P/E": c.forward_pe,
                     "RSI": round(c.rsi, 0), "Ext %": round(c.extension_pct * 100, 1)}
                    for c in picks
                ]
        st.session_state["quality_rows"] = rows

    rows = st.session_state.get("quality_rows")
    if rows is not None:
        if not rows:
            st.info("No names passed the filters (need cached fundamentals).")
        else:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---- Backtest -----------------------------------------------------------


def backtest_view() -> None:
    st.header("📈 Backtest")
    tickers = lib.current_tickers()
    bars = _need_bars(tickers)
    if bars is None:
        return

    c1, c2, c3 = st.columns(3)
    strategy = c1.selectbox("Strategy", ["momentum", "mean_rev"], key="bt_strat")
    initial = float(c2.number_input("Initial capital", 10_000.0, 1e7, 100_000.0, step=10_000.0))
    cost_bps = float(c3.number_input("Cost (bps/side)", 0.0, 100.0, 15.0, step=1.0))

    if strategy == "momentum":
        top_n = int(st.number_input("Top N held", 1, 50, 10, key="bt_topn"))
        kwargs = {"top_n": top_n}
    else:
        d1, d2, d3, d4 = st.columns(4)
        kwargs = {
            "max_concurrent": int(d1.number_input("Max concurrent", 1, 50, 10)),
            "rsi_entry": float(d2.number_input("RSI entry", 5.0, 50.0, 30.0)),
            "rsi_exit": float(d3.number_input("RSI exit", 50.0, 95.0, 60.0)),
            "max_holding_days": int(d4.number_input("Max holding days", 1, 250, 30)),
        }

    if st.button("Run backtest", type="primary"):
        from trading.backtest import mean_rev_bt, momentum_bt
        from trading.backtest.metrics import annual_breakdown, compute_metrics

        with st.spinner("Backtesting…"):
            mod = momentum_bt if strategy == "momentum" else mean_rev_bt
            result = mod.run(bars, initial_capital=initial, cost_bps=cost_bps, **kwargs)
            st.session_state["bt"] = {
                "gross": compute_metrics(result.gross_returns),
                "net": compute_metrics(result.returns),
                "annual": annual_breakdown(result.returns),
                "equity": result.equity,
                "trades": result.trades,
                "strategy": strategy,
            }

    bt = st.session_state.get("bt")
    if bt is None:
        return
    if bt["equity"].empty:
        st.info("Not enough history for this strategy/universe.")
        return

    g, n = bt["gross"], bt["net"]
    mcols = st.columns(4)
    mcols[0].metric("CAGR (net)", f"{n.cagr * 100:.1f}%")
    mcols[1].metric("Sharpe (net)", f"{n.sharpe:.2f}")
    mcols[2].metric("Max drawdown", f"{n.max_drawdown * 100:.1f}%")
    mcols[3].metric("Monthly win rate", f"{n.monthly_win_rate * 100:.0f}%")

    st.caption(f"Gross CAGR {g.cagr * 100:.1f}% · Sharpe {g.sharpe:.2f} "
               f"(net figures shown above include {cost_bps:.0f} bps/side costs)")

    st.subheader("Equity curve (net)")
    st.line_chart(bt["equity"])

    annual = bt["annual"]
    if not annual.empty:
        st.subheader("Annual return")
        st.bar_chart(annual["return"])
        st.dataframe(annual, width="stretch")

    trades = bt["trades"]
    if trades is not None and not trades.empty:
        st.subheader(f"Trades ({len(trades)})")
        st.dataframe(trades, hide_index=True, width="stretch")


# ---- Paper book ---------------------------------------------------------


def paper_book() -> None:
    st.header("📓 Paper book")
    from trading.brokers import BpsFeeModel, PaperBroker
    from trading.execution import PaperBook, summarize
    from trading.storage.state import StateStore

    tickers = lib.current_tickers()
    bars = lib.load_bars(tickers)

    with st.expander("Open today's ideas as positions"):
        c1, c2, c3 = st.columns(3)
        strat = c1.selectbox("Strategy", ["momentum", "mean_rev"], key="pb_strat")
        top_n = int(c2.number_input("Top N", 1, 50, 10, key="pb_topn"))
        short_n = int(c3.number_input("Short N", 0, 20, 0, key="pb_shortn"))
        if st.button("Open positions"):
            if bars.empty:
                st.error("No bars for this universe.")
            else:
                risk = lib.risk_config()
                if strat == "mean_rev":
                    from trading.decision.mean_rev_live import build_mean_rev_recommendations

                    recs = build_mean_rev_recommendations(bars, risk, top_n=top_n,
                                                           allow_short=short_n > 0)
                else:
                    from trading.decision.recommend import build_recommendations

                    recs = build_recommendations(bars, risk, top_n=top_n, short_n=short_n)
                with StateStore(STATE_SQLITE_PATH) as state:
                    ids = PaperBook(state, PaperBroker()).open(recs, strat)
                st.success(f"Opened {len(ids)} positions.")

    cc1, cc2 = st.columns(2)
    if cc1.button("🔄 Update (close stops/targets/time)"):
        with StateStore(STATE_SQLITE_PATH) as state:
            reasons = PaperBook(state, PaperBroker(BpsFeeModel())).update(bars)
        st.success(f"Closed: {reasons or 'none'}")
    max_hold = int(cc2.number_input("Time-stop (days)", 1, 250, 60))

    if not lib.has_state_db():
        st.info("No positions yet.")
        return

    with StateStore(STATE_SQLITE_PATH) as state:
        s = summarize(state, bars if not bars.empty else None)
        open_pos = state.get_positions("open")
        closed = state.get_positions("closed")

    k = st.columns(5)
    k[0].metric("Open", s.open_count)
    k[1].metric("Closed", s.closed_count)
    k[2].metric("Realized ₹", f"{s.realized_pnl:,.0f}")
    k[3].metric("Unrealized ₹", f"{s.unrealized_pnl:,.0f}")
    k[4].metric("Win rate", f"{s.win_rate * 100:.0f}%")
    st.caption(f"Total fees paid: ₹{s.total_fees:,.0f}  ·  time-stop set to {max_hold}d on update")

    if not open_pos.empty:
        st.subheader("Open positions")
        st.dataframe(open_pos, hide_index=True, width="stretch")
    if not closed.empty:
        st.subheader("Closed positions")
        st.dataframe(closed, hide_index=True, width="stretch")

    with st.expander("⚠ Reset paper book"):
        if st.checkbox("Yes, delete all paper state") and st.button("Delete book"):
            Path(STATE_SQLITE_PATH).unlink(missing_ok=True)
            st.success("Paper book deleted. Reload the page.")


# ---- News & quotes ------------------------------------------------------


def news_view() -> None:
    st.header("🗞 News & market")

    st.subheader("Headlines + LLM sentiment")
    c1, c2, c3 = st.columns([2, 1, 1])
    ticker = c1.text_input("Ticker", value="RELIANCE.NS")
    limit = int(c2.number_input("Headlines", 1, 20, 8))
    assess = c3.checkbox("LLM assess")
    if st.button("Fetch news"):
        try:
            from trading.agents import fetch_headlines

            headlines = fetch_headlines(ticker, limit=limit)
        except RuntimeError as exc:
            st.warning(str(exc))
            headlines = []
        st.session_state["news_items"] = [(h.title, h.source, h.link) for h in headlines]
        if assess and headlines:
            try:
                from trading.agents import assess_ticker

                a = assess_ticker(ticker, headlines)
                st.session_state["news_assess"] = a
            except RuntimeError as exc:
                st.session_state["news_assess"] = None
                st.warning(f"LLM assessment unavailable: {exc}")

    items = st.session_state.get("news_items")
    if items:
        a = st.session_state.get("news_assess")
        if a is not None:
            color = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(a.sentiment, "⚪")
            st.metric(f"{color} {a.sentiment.upper()}",
                      f"score {a.score:+.2f}", f"confidence {a.confidence:.0%}")
            st.write(a.summary)
            if a.events:
                st.write("**Events:** " + "; ".join(a.events))
        for title, source, link in items:
            st.markdown(f"- [{title}]({link})" + (f"  *({source})*" if source else ""))

    st.divider()
    st.subheader("Quotes (delayed)")
    qtext = st.text_input("Tickers (space/comma separated)", value="RELIANCE.NS TCS.NS")
    if st.button("Get quotes"):
        from trading.data.realtime import get_quotes

        syms = [s for s in qtext.replace(",", " ").split() if s]
        with st.spinner("Fetching quotes…"):
            quotes = get_quotes(syms)
        rows = [
            {"Ticker": t, "Price": q.price, "Prev close": q.prev_close,
             "Change %": round(q.change_pct * 100, 2) if q.change_pct is not None else None,
             "Currency": q.currency}
            for t, q in quotes.items()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---- Config -------------------------------------------------------------


def config_view() -> None:
    st.header("⚙ Configuration & data")

    st.subheader("Data status")
    status = lib.data_status()
    st.json({**{k: str(v) for k, v in status.items()},
             "fundamentals_cached": lib.fundamentals_count(),
             "active_universe": lib.universe_label()})

    st.subheader("Ingest daily bars (network)")
    c1, c2, c3 = st.columns(3)
    uni = c1.selectbox("Universe", lib.UNIVERSES, index=lib.UNIVERSES.index(
        st.session_state.get("universe", "nifty50")))
    source = c2.selectbox("Source", ["yfinance", "jugaad"])
    hist = int(c3.number_input("History days", 100, 2500, 400, step=100))
    if st.button("Ingest now"):
        from trading.config.settings import BARS_DUCKDB_PATH
        from trading.config.universe import get_universe

        if source == "jugaad":
            from trading.data.jugaad_ingest import ingest_universe
        else:
            from trading.data.yfinance_ingest import ingest_universe
        with st.spinner(f"Ingesting {uni} via {source} (this can take a while)…"):
            with BarsStore_ctx(BARS_DUCKDB_PATH) as store:
                counts = ingest_universe(store, get_universe(uni), history_days=hist)
        lib.load_bars.clear() if hasattr(lib.load_bars, "clear") else None
        st.cache_data.clear()
        ok = sum(1 for v in counts.values() if v > 0)
        st.success(f"Ingested {sum(counts.values()):,} rows across {ok} tickers via {source}.")

    st.subheader("Frozen-universe snapshots (survivorship)")
    st.caption("Snapshots freeze *current* index members to a dated file for "
               "reproducible runs. They do not remove survivorship bias.")
    sc1, sc2 = st.columns(2)
    snap_uni = sc1.selectbox("Universe to snapshot", lib.UNIVERSES, key="snap_uni")
    if sc2.button("Create snapshot"):
        from trading.config.universe import snapshot_universe

        p = snapshot_universe(snap_uni, lib.UNIVERSES_DIR)
        st.success(f"Saved {p.name}")
    snaps = sorted(lib.UNIVERSES_DIR.glob("*.json")) if lib.UNIVERSES_DIR.exists() else []
    if snaps:
        chosen = st.selectbox("Activate a snapshot", ["(none)"] + [p.name for p in snaps])
        if chosen != "(none)":
            st.session_state["snapshot_path"] = str(lib.UNIVERSES_DIR / chosen)
            st.caption(f"Active snapshot: {chosen}")
        elif st.session_state.get("snapshot_path"):
            if st.button("Clear active snapshot"):
                st.session_state["snapshot_path"] = ""

    st.subheader("Current risk config")
    st.json(lib.risk_config().model_dump())

    st.subheader("Run metrics log")
    m = lib.recent_metrics(50)
    if m.empty:
        st.caption("No runs recorded.")
    else:
        st.dataframe(m, hide_index=True, width="stretch")
    st.caption(f"Log file: {LOGS_DIR / 'metrics.jsonl'}")


def BarsStore_ctx(path):  # small indirection so tests can import views without duckdb open
    from trading.storage.bars import BarsStore

    return BarsStore(path)
