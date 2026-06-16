from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading.brokers import BpsFeeModel, Order, PaperBroker
from trading.execution import PaperBook
from trading.storage.state import StateStore


@dataclass
class _Rec:
    ticker: str
    direction: str
    entry: float
    stop: float
    target: float
    shares: int
    notional: float
    risk_inr: float
    conviction: int
    score: float
    as_of: pd.Timestamp
    rationale: str = "test"


def _bars(ticker, rows):
    """rows: list of (date, high, low, close)."""
    return pd.DataFrame(
        [
            {"ticker": ticker, "date": d, "open": c, "high": h, "low": lo,
             "close": c, "adj_close": c, "volume": 1000}
            for (d, h, lo, c) in rows
        ]
    )


def test_paper_broker_slippage_and_fee():
    bk = PaperBroker(BpsFeeModel(bps_per_side=10), slippage_bps=20)
    fill = bk.place(Order("X", "buy", 10, 100.0))
    assert round(fill.price, 4) == 100.2          # +20 bps adverse on a buy
    assert round(fill.fee, 4) == round(100.2 * 10 * 10 / 10_000, 4)
    fill_sell = bk.place(Order("X", "sell", 10, 100.0))
    assert round(fill_sell.price, 4) == 99.8       # -20 bps adverse on a sell


def test_long_target_hit(tmp_state_path):
    rec = _Rec("UPA.NS", "LONG", 100.0, 95.0, 110.0, 10, 1000.0, 50.0, 5, 0.4,
               pd.Timestamp("2024-01-02"))
    bars = _bars("UPA.NS", [
        ("2024-01-03", 105, 99, 104),    # nothing
        ("2024-01-04", 112, 108, 111),   # target 110 hit
    ])
    with StateStore(tmp_state_path) as st:
        book = PaperBook(st, PaperBroker())
        book.open([rec], "momentum")
        reasons = book.update(bars)
        assert reasons == {"target": 1}
        s = book.summary(bars)
        assert s.closed_count == 1 and s.open_count == 0
        assert round(s.realized_pnl, 2) == 100.0   # (110-100)*10
        assert s.win_rate == 1.0
        assert s.total_fees > 0


def test_long_stop_hit_before_target(tmp_state_path):
    rec = _Rec("UPA.NS", "LONG", 100.0, 95.0, 110.0, 10, 1000.0, 50.0, 5, 0.4,
               pd.Timestamp("2024-01-02"))
    # same day touches both stop and target → conservative: stop first
    bars = _bars("UPA.NS", [("2024-01-03", 111, 94, 100)])
    with StateStore(tmp_state_path) as st:
        book = PaperBook(st, PaperBroker())
        book.open([rec], "momentum")
        reasons = book.update(bars)
        assert reasons == {"stop": 1}
        assert round(book.summary().realized_pnl, 2) == -50.0  # (95-100)*10


def test_short_target_hit(tmp_state_path):
    rec = _Rec("DOWNA.NS", "SHORT", 400.0, 420.0, 380.0, 5, 2000.0, 100.0, 5, -0.2,
               pd.Timestamp("2024-01-02"))
    bars = _bars("DOWNA.NS", [("2024-01-03", 405, 378, 382)])  # low 378 <= target 380
    with StateStore(tmp_state_path) as st:
        book = PaperBook(st, PaperBroker())
        book.open([rec], "momentum")
        assert book.update(bars) == {"target": 1}
        assert round(book.summary().realized_pnl, 2) == 100.0  # (400-380)*5


def test_time_stop(tmp_state_path):
    rec = _Rec("FLATA.NS", "LONG", 100.0, 80.0, 130.0, 10, 1000.0, 50.0, 3, 0.1,
               pd.Timestamp("2024-01-02"))
    # never hits stop/target; a bar 40 days later forces a time exit
    bars = _bars("FLATA.NS", [
        ("2024-01-03", 101, 99, 100),
        ("2024-02-20", 102, 98, 101),    # > 30 days later
    ])
    with StateStore(tmp_state_path) as st:
        book = PaperBook(st, PaperBroker())
        book.open([rec], "momentum")
        assert book.update(bars, max_holding_days=30) == {"time": 1}
