from __future__ import annotations

from trading.config.settings import RiskConfig
from trading.decision.recommend import build_recommendations, stop_and_target


def test_stop_and_target_directions():
    # long: stop below, target above
    stop, target = stop_and_target("LONG", 100.0, 5.0, 2.0)
    assert stop == 95.0 and target == 110.0
    # short: stop above, target below
    stop, target = stop_and_target("SHORT", 100.0, 5.0, 2.0)
    assert stop == 105.0 and target == 90.0


def test_long_only_recommendations(synth_bars):
    risk = RiskConfig()
    recs = build_recommendations(synth_bars, risk, top_n=4)
    assert recs, "expected at least one long recommendation"
    assert all(r.direction == "LONG" for r in recs)
    for r in recs:
        assert r.stop < r.entry < r.target
        assert r.shares > 0
        assert r.conviction in range(1, 6)
        # risk per trade respects the 2% ceiling
        assert r.risk_inr <= risk.capital_inr * risk.max_risk_per_trade_pct + 1e-6


def test_long_short_book(synth_bars):
    risk = RiskConfig()
    recs = build_recommendations(synth_bars, risk, top_n=3, short_n=2)
    longs = [r for r in recs if r.direction == "LONG"]
    shorts = [r for r in recs if r.direction == "SHORT"]
    assert longs, "expected longs"
    assert shorts, "expected shorts from negative-momentum laggards"
    for r in shorts:
        assert r.stop > r.entry > r.target  # mirrored levels
        assert r.score < 0  # only short negative-momentum names


def test_risk_based_sizing_mode(synth_bars):
    risk = RiskConfig(sizing_mode="risk_based")
    recs = build_recommendations(synth_bars, risk, top_n=4)
    assert recs
    # risk-based: shares ≈ (1% capital) / stop_dist, so risk_inr ≈ 1% capital
    for r in recs:
        assert r.risk_inr <= risk.capital_inr * risk.risk_per_trade_pct + r.entry
