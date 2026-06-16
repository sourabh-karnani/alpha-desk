from __future__ import annotations

import json

import pytest

from trading.config.universe import get_universe, load_snapshot, snapshot_universe


def test_get_universe_names():
    assert len(get_universe("nifty50")) == 50
    assert len(get_universe("nifty100")) == len(get_universe("nifty50")) + len(
        get_universe("nifty_next_50")
    )
    assert all(t.isupper() for t in get_universe("sp100"))
    with pytest.raises(ValueError):
        get_universe("does-not-exist")


def test_snapshot_roundtrip(tmp_path):
    from datetime import date

    path = snapshot_universe("nifty50", tmp_path, as_of=date(2024, 1, 2))
    assert path.name == "nifty50_2024-01-02.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["name"] == "nifty50"
    assert payload["as_of"] == "2024-01-02"
    assert "survivorship" in payload["source"].lower()
    assert load_snapshot(path) == get_universe("nifty50")
