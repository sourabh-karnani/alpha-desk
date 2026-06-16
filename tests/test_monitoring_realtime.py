from __future__ import annotations

import time

from trading.data import realtime
from trading.monitoring import Timer, read_events, record_event


def test_record_and_read_events(tmp_path):
    record_event("report", {"strategy": "momentum", "n_recs": 5}, tmp_path)
    record_event("report", {"strategy": "mean_rev", "n_recs": 2}, tmp_path)
    record_event("paper-run", {"opened": 3}, tmp_path)

    all_df = read_events(tmp_path)
    assert len(all_df) == 3
    reports = read_events(tmp_path, name="report")
    assert len(reports) == 2
    assert set(reports["strategy"]) == {"momentum", "mean_rev"}


def test_read_events_missing_file(tmp_path):
    df = read_events(tmp_path / "nope")
    assert df.empty


def test_timer():
    with Timer() as t:
        time.sleep(0.01)
    assert t.seconds >= 0.01


class _FakeFastInfo(dict):
    pass


def test_get_quote_computes_change(monkeypatch):
    class _FakeTicker:
        def __init__(self, ticker):
            self.fast_info = _FakeFastInfo(
                last_price=110.0, previous_close=100.0, currency="INR"
            )

    monkeypatch.setattr(realtime.yf, "Ticker", _FakeTicker)
    q = realtime.get_quote("X.NS")
    assert q.price == 110.0
    assert round(q.change_pct, 4) == 0.10
    assert q.currency == "INR"


def test_get_quote_handles_failure(monkeypatch):
    class _BoomTicker:
        def __init__(self, ticker):
            raise RuntimeError("network down")

    monkeypatch.setattr(realtime.yf, "Ticker", _BoomTicker)
    q = realtime.get_quote("X.NS")
    assert q.price is None and q.change_pct is None
