"""Smoke tests for the Streamlit dashboard.

Uses Streamlit's AppTest to run each page renderer headlessly and assert it
draws without raising. Robust to a missing data store: the pages degrade to a
warning rather than erroring when no bars are present. Skipped entirely if the
`web` extra (streamlit) isn't installed.
"""
from __future__ import annotations

import importlib.util

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("streamlit") is None, reason="web extra not installed"
)


@pytest.mark.parametrize("view_name", [
    "dashboard", "ideas", "intraday", "quality",
    "backtest_view", "paper_book", "news_view", "config_view",
])
def test_view_renders_without_exception(view_name):
    from streamlit.testing.v1 import AppTest

    # from_string runs the source as a real script (keeps imports), unlike
    # from_function which strips the module namespace.
    script = (
        "import streamlit as st\n"
        "from trading.web import lib, views\n"
        "lib.init_state()\n"
        f"views.{view_name}()\n"
    )
    at = AppTest.from_string(script, default_timeout=60)
    at.run()
    assert not at.exception, f"{view_name} raised: {list(at.exception)}"


def test_app_entry_runs():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/trading/web/app.py", default_timeout=60)
    at.run()
    assert not at.exception, f"app.py raised: {list(at.exception)}"
