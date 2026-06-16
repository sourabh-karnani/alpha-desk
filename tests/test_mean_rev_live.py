from __future__ import annotations

from trading.config.settings import RiskConfig
from trading.decision.mean_rev_live import build_mean_rev_recommendations


def test_returns_list_and_invariants(synth_bars):
    risk = RiskConfig()
    recs = build_mean_rev_recommendations(synth_bars, risk, top_n=10, allow_short=True)
    assert isinstance(recs, list)
    for r in recs:
        if r.direction == "LONG":
            assert r.stop < r.entry < r.target
        else:
            assert r.stop > r.entry > r.target
        assert r.shares >= 0


def test_empty_on_insufficient_data():
    import pandas as pd

    tiny = pd.DataFrame(
        {
            "ticker": ["X"] * 5,
            "date": pd.bdate_range("2024-01-01", periods=5).date,
            "open": [1, 2, 3, 4, 5],
            "high": [1, 2, 3, 4, 5],
            "low": [1, 2, 3, 4, 5],
            "close": [1, 2, 3, 4, 5],
            "adj_close": [1, 2, 3, 4, 5],
            "volume": [1, 1, 1, 1, 1],
        }
    )
    assert build_mean_rev_recommendations(tiny, RiskConfig()) == []
