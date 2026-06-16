from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading.storage.state import StateStore, _signed_pnl


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
    rationale: str


def _rec(ticker="UPA.NS", direction="LONG", entry=100.0):
    return _Rec(ticker, direction, entry, entry * 0.95, entry * 1.10, 10,
                entry * 10, 50.0, 5, 0.42, pd.Timestamp("2024-01-02"), "because")


def test_signed_pnl_long_and_short():
    pnl, pct = _signed_pnl("LONG", 100.0, 110.0, 10)
    assert pnl == 100.0
    assert round(pct, 4) == 0.10
    pnl, pct = _signed_pnl("SHORT", 100.0, 90.0, 10)
    assert pnl == 100.0
    assert round(pct, 4) == round(100.0 / 90.0 - 1.0, 4)


def test_record_and_lifecycle(tmp_state_path):
    with StateStore(tmp_state_path) as st:
        ids = st.record_recommendations([_rec(), _rec("DOWNA.NS", "SHORT", 400.0)], "momentum")
        assert len(ids) == 2
        recs = st.get_recommendations()
        assert len(recs) == 2
        assert set(recs["status"]) == {"new"}

        pos_id = st.open_position(
            "UPA.NS", "LONG", 10, 100.0, "2024-01-03",
            stop=95.0, target=110.0, rec_id=ids[0], fee=1.5,
        )
        assert len(st.get_positions("open")) == 1
        # recommendation flips to 'filled'
        assert st.get_recommendations().set_index("id").loc[ids[0], "status"] == "filled"

        st.close_position(pos_id, exit_price=110.0, exit_date="2024-01-10",
                          exit_reason="target", fee=1.5)
        closed = st.get_positions("closed")
        assert len(closed) == 1
        assert round(float(closed.iloc[0]["pnl"]), 2) == 100.0
        assert st.realized_pnl() == 100.0
        # 2 fills (entry + exit), fees summed
        assert len(st.get_fills()) == 2
        assert st.total_fees() == 3.0


def test_short_position_pnl(tmp_state_path):
    with StateStore(tmp_state_path) as st:
        pos_id = st.open_position("DOWNA.NS", "SHORT", 5, 400.0, "2024-01-03", stop=420.0)
        st.close_position(pos_id, exit_price=380.0, exit_date="2024-01-09",
                          exit_reason="target")
        row = st.get_positions("closed").iloc[0]
        assert round(float(row["pnl"]), 2) == 100.0  # (400-380)*5
