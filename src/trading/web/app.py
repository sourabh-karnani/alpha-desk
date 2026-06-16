"""Streamlit entry point for the alpha-desk dashboard.

Launch via `uv run trading web` (or `streamlit run src/trading/web/app.py`).
The left sidebar holds global config (universe + risk) shared by every page;
pages are defined in `views.py`.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from trading.web import lib, views


def _sidebar() -> None:
    st.title("📈 alpha-desk")
    st.caption("Personal trading research console")

    st.selectbox("Universe", lib.UNIVERSES, key="universe")
    snap = st.session_state.get("snapshot_path")
    if snap:
        st.info(f"Snapshot active: **{Path(snap).name}** (overrides universe). "
                "Clear it on the Config page.")

    st.number_input("Capital ₹", min_value=10_000.0, max_value=1e8,
                    step=10_000.0, key="capital")
    st.selectbox("Sizing mode", ["equal_weight", "risk_based"], key="sizing_mode")

    cc1, cc2 = st.columns(2)
    cc1.number_input("Max positions", min_value=1, max_value=50, key="max_positions")
    cc2.number_input("ATR stop ×", min_value=0.5, max_value=10.0, step=0.5, key="atr_mult")
    st.number_input("Reward : risk", min_value=0.5, max_value=10.0, step=0.5, key="rr")

    with st.expander("Advanced risk (fractions of capital)"):
        st.number_input("Risk per trade (risk_based)", min_value=0.001, max_value=0.10,
                        step=0.005, format="%.3f", key="risk_per_trade_pct")
        st.number_input("Risk ceiling (equal_weight)", min_value=0.001, max_value=0.10,
                        step=0.005, format="%.3f", key="max_risk_pct")
        st.number_input("Max position size", min_value=0.01, max_value=1.0,
                        step=0.01, format="%.2f", key="max_position_pct")

    st.divider()
    st.caption("Paper-only research tooling. Not investment advice.")


def main() -> None:
    st.set_page_config(page_title="alpha-desk", page_icon="📈", layout="wide")
    lib.init_state()

    pages = [
        st.Page(views.dashboard, title="Dashboard", icon="📊", default=True),
        st.Page(views.ideas, title="Recommendations", icon="💡"),
        st.Page(views.intraday, title="Intraday", icon="⚡"),
        st.Page(views.quality, title="Quality & Composite", icon="🔎"),
        st.Page(views.backtest_view, title="Backtest", icon="📈"),
        st.Page(views.paper_book, title="Paper Book", icon="📓"),
        st.Page(views.news_view, title="News & Market", icon="🗞"),
        st.Page(views.config_view, title="Config & Data", icon="⚙"),
    ]
    nav = st.navigation(pages)
    with st.sidebar:
        _sidebar()
    nav.run()


main()
