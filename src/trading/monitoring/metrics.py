"""Append-only JSONL run log under the logs directory.

`record_event` is fire-and-forget: it never raises into the caller (a metrics
failure must not break a report run). `read_events` loads the log back for
inspection / a `trading metrics` view.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_METRICS_FILE = "metrics.jsonl"


def _now() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def record_event(name: str, fields: dict, logs_dir: Path) -> None:
    try:
        logs_dir = Path(logs_dir)
        logs_dir.mkdir(parents=True, exist_ok=True)
        row = {"ts": _now(), "event": name, **fields}
        with (logs_dir / _METRICS_FILE).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001 — monitoring must never break the caller
        log.warning("record_event failed: %s", exc)


def read_events(logs_dir: Path, name: str | None = None) -> pd.DataFrame:
    path = Path(logs_dir) / _METRICS_FILE
    if not path.exists():
        return pd.DataFrame(columns=["ts", "event"])
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    df = pd.DataFrame(rows)
    if name and not df.empty and "event" in df.columns:
        df = df[df["event"] == name]
    return df.reset_index(drop=True)


class Timer:
    """Context manager that records wall-clock seconds in `.seconds`."""

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        self.seconds = 0.0
        return self

    def __exit__(self, *_) -> None:
        self.seconds = time.perf_counter() - self._start
