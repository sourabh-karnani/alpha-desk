from __future__ import annotations

import pandas as pd

from trading.data.jugaad_ingest import _normalize, nse_symbol


def test_nse_symbol():
    assert nse_symbol("SBIN.NS") == "SBIN"
    assert nse_symbol("RELIANCE") == "RELIANCE"


def test_normalize_nse_frame():
    # jugaad-style columns (mixed case), including an LTP that should be ignored
    raw = pd.DataFrame(
        {
            "DATE": ["2024-01-01", "2024-01-02"],
            "OPEN": [100.0, 102.0],
            "HIGH": [105.0, 104.0],
            "LOW": [99.0, 101.0],
            "CLOSE": [104.0, 103.0],
            "LTP": [104.1, 103.1],
            "VOLUME": [1000, 2000],
        }
    )
    out = _normalize(raw, "SBIN.NS")
    assert list(out.columns) == [
        "ticker", "date", "open", "high", "low", "close", "adj_close", "volume",
    ]
    assert (out["ticker"] == "SBIN.NS").all()
    # NSE has no adjusted close → adj_close mirrors close
    assert (out["adj_close"] == out["close"]).all()
    assert out["volume"].dtype == "int64"
    assert len(out) == 2


def test_normalize_empty():
    assert _normalize(pd.DataFrame(), "X.NS").empty
