"""Smoke tests: the package imports and core public surfaces exist."""
from __future__ import annotations

import importlib

import pandas as pd


def test_package_imports():
    import trading

    assert trading.__version__


def test_core_modules_import():
    for mod in (
        "trading.cli",
        "trading.config.settings",
        "trading.config.universe",
        "trading.signals.momentum",
        "trading.signals.mean_reversion",
        "trading.decision.recommend",
        "trading.backtest.portfolio",
        "trading.reporting.markdown",
    ):
        assert importlib.import_module(mod) is not None


def test_synth_bars_shape(synth_bars: pd.DataFrame):
    assert set(synth_bars["ticker"].unique()) == {
        "UPA.NS", "UPB.NS", "DOWNA.NS", "DOWNB.NS", "FLATA.NS", "FLATB.NS",
    }
    assert {"open", "high", "low", "close", "adj_close", "volume"} <= set(synth_bars.columns)
    # high >= low on every row
    assert (synth_bars["high"] >= synth_bars["low"]).all()
