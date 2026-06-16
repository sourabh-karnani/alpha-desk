"""End-to-end CLI tests driving the real report pipeline on synthetic data."""
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from trading import cli as cli_mod
from trading.storage.bars import BarsStore


@pytest.fixture
def wired_cli(tmp_path, synth_bars, monkeypatch):
    bars_path = tmp_path / "bars.duckdb"
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    with BarsStore(bars_path) as store:
        store.upsert(synth_bars)

    snap = tmp_path / "synth.json"
    snap.write_text(
        json.dumps({"name": "synth", "as_of": "2024-01-02", "source": "test",
                    "tickers": sorted(synth_bars["ticker"].unique())}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli_mod, "BARS_DUCKDB_PATH", bars_path)
    monkeypatch.setattr(cli_mod, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(cli_mod, "STATE_SQLITE_PATH", tmp_path / "state.sqlite")
    return {"snapshot": str(snap), "reports": reports_dir}


def test_report_momentum_long_short(wired_cli):
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["report", "--snapshot", wired_cli["snapshot"], "--top-n", "3", "--short-n", "2"],
    )
    assert result.exit_code == 0, result.output
    assert "recommendations" in result.output
    assert list(wired_cli["reports"].glob("*.md")), "no report written"


def test_report_mean_rev(wired_cli):
    runner = CliRunner()
    result = runner.invoke(
        cli_mod.cli,
        ["report", "--snapshot", wired_cli["snapshot"], "--strategy", "mean_rev",
         "--allow-short"],
    )
    assert result.exit_code == 0, result.output


def test_paper_run_and_status(wired_cli):
    runner = CliRunner()
    run = runner.invoke(
        cli_mod.cli,
        ["paper-run", "--snapshot", wired_cli["snapshot"], "--top-n", "3", "--short-n", "1"],
    )
    assert run.exit_code == 0, run.output
    assert "Opened" in run.output

    status = runner.invoke(cli_mod.cli, ["paper-status", "--snapshot", wired_cli["snapshot"]])
    assert status.exit_code == 0, status.output
    assert "Paper book" in status.output

    upd = runner.invoke(cli_mod.cli, ["paper-update", "--snapshot", wired_cli["snapshot"]])
    assert upd.exit_code == 0, upd.output


def test_help_lists_commands():
    result = CliRunner().invoke(cli_mod.cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("report", "backtest", "ingest", "universe-snapshot",
                "paper-run", "paper-update", "paper-status"):
        assert cmd in result.output
