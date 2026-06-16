"""SQLite state store for the paper-trading lifecycle.

Holds three things that must survive across CLI invocations:

* ``recommendations`` — every idea the engine has emitted (an audit trail),
* ``positions``       — paper positions opened from those ideas, and
* ``fills``           — the individual buy/sell/short/cover events.

This is deliberately a thin, dependency-free wrapper over ``sqlite3`` (stdlib
only) so it sits *below* the broker / execution / decision layers and can be
imported by all of them without creating a cycle. It accepts duck-typed
recommendation objects (anything exposing ``ticker``, ``direction``, ``entry``,
``stop``, ``target``, ``shares``, ``notional``, ``risk_inr``, ``conviction``,
``score``, ``as_of`` and ``rationale``) rather than importing the concrete
``Recommendation`` dataclass.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS recommendations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    as_of       TEXT,
    strategy    TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    direction   TEXT NOT NULL,
    entry       REAL,
    stop        REAL,
    target      REAL,
    shares      INTEGER,
    notional    REAL,
    risk_inr    REAL,
    conviction  INTEGER,
    score       REAL,
    rationale   TEXT,
    status      TEXT NOT NULL DEFAULT 'new'
);

CREATE TABLE IF NOT EXISTS positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_id       INTEGER,
    ticker       TEXT NOT NULL,
    direction    TEXT NOT NULL,
    qty          INTEGER NOT NULL,
    entry_price  REAL NOT NULL,
    entry_date   TEXT NOT NULL,
    stop         REAL,
    target       REAL,
    status       TEXT NOT NULL DEFAULT 'open',
    exit_price   REAL,
    exit_date    TEXT,
    exit_reason  TEXT,
    pnl          REAL,
    pnl_pct      REAL,
    FOREIGN KEY (rec_id) REFERENCES recommendations(id)
);

CREATE TABLE IF NOT EXISTS fills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id  INTEGER,
    ts           TEXT NOT NULL,
    ticker       TEXT NOT NULL,
    side         TEXT NOT NULL,
    qty          INTEGER NOT NULL,
    price        REAL NOT NULL,
    fee          REAL NOT NULL DEFAULT 0.0,
    FOREIGN KEY (position_id) REFERENCES positions(id)
);

CREATE INDEX IF NOT EXISTS idx_pos_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_rec_status ON recommendations(status);
"""

_REC_FIELDS = (
    "ticker", "direction", "entry", "stop", "target",
    "shares", "notional", "risk_inr", "conviction", "score", "rationale",
)


def _utcnow() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _signed_pnl(direction: str, entry: float, exit_price: float, qty: int) -> tuple[float, float]:
    """Return (pnl_cash, pnl_pct) for a long or short position."""
    if entry <= 0:
        return 0.0, 0.0
    if direction.upper() == "SHORT":
        pnl_pct = entry / exit_price - 1.0 if exit_price > 0 else 0.0
        pnl = (entry - exit_price) * qty
    else:
        pnl_pct = exit_price / entry - 1.0
        pnl = (exit_price - entry) * qty
    return float(pnl), float(pnl_pct)


class StateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ---- recommendations -------------------------------------------------
    def record_recommendations(self, recs: Iterable, strategy: str) -> list[int]:
        """Persist an audit trail of emitted ideas. Returns the new row ids."""
        ids: list[int] = []
        created = _utcnow()
        for r in recs:
            as_of = getattr(r, "as_of", None)
            as_of_s = as_of.isoformat() if hasattr(as_of, "isoformat") else (
                str(as_of) if as_of is not None else None
            )
            vals = [getattr(r, f, None) for f in _REC_FIELDS]
            cur = self._conn.execute(
                f"INSERT INTO recommendations "
                f"(created_at, as_of, strategy, {','.join(_REC_FIELDS)}) "
                f"VALUES (?,?,?,{','.join(['?'] * len(_REC_FIELDS))})",
                [created, as_of_s, strategy, *vals],
            )
            ids.append(int(cur.lastrowid))
        self._conn.commit()
        return ids

    def get_recommendations(self, status: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM recommendations"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id"
        return pd.read_sql_query(sql, self._conn, params=params)

    def set_recommendation_status(self, rec_id: int, status: str) -> None:
        self._conn.execute(
            "UPDATE recommendations SET status = ? WHERE id = ?", [status, rec_id]
        )
        self._conn.commit()

    # ---- positions -------------------------------------------------------
    def open_position(
        self,
        ticker: str,
        direction: str,
        qty: int,
        entry_price: float,
        entry_date: str,
        stop: float | None = None,
        target: float | None = None,
        rec_id: int | None = None,
        fee: float = 0.0,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO positions "
            "(rec_id, ticker, direction, qty, entry_price, entry_date, stop, target, status) "
            "VALUES (?,?,?,?,?,?,?,?, 'open')",
            [rec_id, ticker, direction, qty, entry_price, entry_date, stop, target],
        )
        pos_id = int(cur.lastrowid)
        side = "short" if direction.upper() == "SHORT" else "buy"
        self.record_fill(pos_id, ticker, side, qty, entry_price, ts=entry_date, fee=fee)
        if rec_id is not None:
            self.set_recommendation_status(rec_id, "filled")
        self._conn.commit()
        return pos_id

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_date: str,
        exit_reason: str,
        fee: float = 0.0,
    ) -> None:
        row = self._conn.execute(
            "SELECT direction, qty, entry_price, ticker, status FROM positions WHERE id = ?",
            [position_id],
        ).fetchone()
        if row is None or row["status"] != "open":
            return
        pnl, pnl_pct = _signed_pnl(row["direction"], row["entry_price"], exit_price, row["qty"])
        self._conn.execute(
            "UPDATE positions SET status='closed', exit_price=?, exit_date=?, "
            "exit_reason=?, pnl=?, pnl_pct=? WHERE id = ?",
            [exit_price, exit_date, exit_reason, pnl, pnl_pct, position_id],
        )
        side = "cover" if row["direction"].upper() == "SHORT" else "sell"
        self.record_fill(position_id, row["ticker"], side, row["qty"], exit_price,
                         ts=exit_date, fee=fee)
        self._conn.commit()

    def get_positions(self, status: str | None = None) -> pd.DataFrame:
        sql = "SELECT * FROM positions"
        params: list = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY id"
        return pd.read_sql_query(sql, self._conn, params=params)

    # ---- fills -----------------------------------------------------------
    def record_fill(
        self,
        position_id: int | None,
        ticker: str,
        side: str,
        qty: int,
        price: float,
        ts: str | None = None,
        fee: float = 0.0,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO fills (position_id, ts, ticker, side, qty, price, fee) "
            "VALUES (?,?,?,?,?,?,?)",
            [position_id, ts or _utcnow(), ticker, side, qty, price, fee],
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_fills(self) -> pd.DataFrame:
        return pd.read_sql_query("SELECT * FROM fills ORDER BY id", self._conn)

    # ---- aggregates ------------------------------------------------------
    def realized_pnl(self) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(pnl), 0.0) AS p FROM positions WHERE status='closed'"
        ).fetchone()
        return float(row["p"])

    def total_fees(self) -> float:
        row = self._conn.execute("SELECT COALESCE(SUM(fee), 0.0) AS f FROM fills").fetchone()
        return float(row["f"])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *_) -> None:
        self.close()
