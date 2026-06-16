from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _synth_ticker(
    ticker: str,
    n: int,
    start_price: float,
    drift: float,
    vol: float,
    seed: int,
    start_date: str = "2023-01-02",
) -> pd.DataFrame:
    """Deterministic synthetic OHLCV for one ticker.

    `drift` is per-day geometric drift; `vol` is per-day return std.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start=start_date, periods=n)
    rets = rng.normal(loc=drift, scale=vol, size=n)
    close = start_price * np.cumprod(1.0 + rets)
    # Build a plausible OHLC envelope around the close path.
    intraday = np.abs(rng.normal(0.0, vol, size=n)) + 1e-4
    high = close * (1.0 + intraday)
    low = close * (1.0 - intraday)
    open_ = (high + low) / 2.0
    volume = rng.integers(100_000, 1_000_000, size=n)
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": dates.date,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "adj_close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def synth_bars() -> pd.DataFrame:
    """A multi-ticker daily-bar panel long enough for 12-1 momentum / SMA200.

    UP* trend strongly upward (momentum leaders), DOWN* trend down (short
    candidates), FLAT* oscillate (mean-reversion candidates).
    """
    n = 320
    frames = [
        _synth_ticker("UPA.NS", n, 100.0, drift=0.0020, vol=0.012, seed=1),
        _synth_ticker("UPB.NS", n, 250.0, drift=0.0015, vol=0.013, seed=2),
        _synth_ticker("DOWNA.NS", n, 400.0, drift=-0.0018, vol=0.014, seed=3),
        _synth_ticker("DOWNB.NS", n, 80.0, drift=-0.0012, vol=0.015, seed=4),
        _synth_ticker("FLATA.NS", n, 150.0, drift=0.0001, vol=0.018, seed=5),
        _synth_ticker("FLATB.NS", n, 600.0, drift=0.0002, vol=0.016, seed=6),
    ]
    return pd.concat(frames).reset_index(drop=True)


@pytest.fixture
def tmp_state_path(tmp_path):
    return tmp_path / "state.sqlite"
