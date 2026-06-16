"""Real-time(ish) last-price quotes via yfinance `fast_info`.

This is not a streaming feed — it's an on-demand snapshot suitable for a
pre-open sanity check or marking the paper book intraday. yfinance quotes are
delayed and best-effort; failures return a Quote with ``price=None`` rather than
raising, so a single bad symbol never aborts a batch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import yfinance as yf

log = logging.getLogger(__name__)


@dataclass
class Quote:
    ticker: str
    price: float | None
    prev_close: float | None
    change_pct: float | None
    currency: str | None
    ts: str


def _now() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def get_quote(ticker: str) -> Quote:
    try:
        fi = yf.Ticker(ticker).fast_info
        price = fi.get("last_price") if hasattr(fi, "get") else getattr(fi, "last_price", None)
        prev = fi.get("previous_close") if hasattr(fi, "get") else getattr(
            fi, "previous_close", None
        )
        currency = fi.get("currency") if hasattr(fi, "get") else getattr(fi, "currency", None)
    except Exception as exc:  # noqa: BLE001 — one bad symbol must not abort a batch
        log.warning("quote failed for %s: %s", ticker, exc)
        return Quote(ticker, None, None, None, None, _now())

    change_pct = None
    if price is not None and prev:
        try:
            change_pct = float(price) / float(prev) - 1.0
        except (TypeError, ZeroDivisionError):
            change_pct = None

    return Quote(
        ticker=ticker,
        price=float(price) if price is not None else None,
        prev_close=float(prev) if prev is not None else None,
        change_pct=change_pct,
        currency=currency,
        ts=_now(),
    )


def get_quotes(tickers: list[str]) -> dict[str, Quote]:
    return {t: get_quote(t) for t in tickers}
