from __future__ import annotations

import logging

import yfinance as yf

from trading.storage.fundamentals import FundamentalsStore

log = logging.getLogger(__name__)

# Our fundamentals column -> the corresponding key on yfinance Ticker.info.
_FIELD_MAP = {
    "short_name": "shortName",
    "sector": "sector",
    "industry": "industry",
    "market_cap": "marketCap",
    "forward_pe": "forwardPE",
    "trailing_pe": "trailingPE",
    "trailing_eps": "trailingEps",
    "forward_eps": "forwardEps",
    "price_to_book": "priceToBook",
    "price_to_sales": "priceToSalesTrailing12Months",
    "profit_margin": "profitMargins",
    "roe": "returnOnEquity",
    "debt_to_equity": "debtToEquity",
    "revenue_growth": "revenueGrowth",
    "earnings_growth": "earningsGrowth",
    "analyst_target": "targetMeanPrice",
    "analyst_recommendation": "recommendationKey",
    "num_analysts": "numberOfAnalystOpinions",
    "beta": "beta",
    "fifty_two_week_high": "fiftyTwoWeekHigh",
    "fifty_two_week_low": "fiftyTwoWeekLow",
    "dividend_yield": "dividendYield",
}


def fetch_ticker(ticker: str) -> dict | None:
    """Pull fundamentals for one ticker from yfinance. None on failure/empty."""
    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:  # noqa: BLE001 — keep the universe loop going
        log.warning("fundamentals fetch failed for %s: %s", ticker, exc)
        return None
    if not info:
        return None
    return {col: info.get(src) for col, src in _FIELD_MAP.items()}


def fetch_universe(
    tickers: list[str],
    store: FundamentalsStore,
    max_age_days: int = 7,
) -> dict[str, str]:
    """Ensure fundamentals exist (and are fresh) for each ticker.

    Returns {ticker: status} where status is one of "cached" (still fresh,
    skipped), "fetched" (pulled and stored), or "error" (fetch failed).
    `max_age_days=0` forces a refresh of every ticker.
    """
    results: dict[str, str] = {}
    total = len(tickers)
    for i, ticker in enumerate(tickers, 1):
        if max_age_days > 0 and not store.is_stale(ticker, max_age_days=max_age_days):
            results[ticker] = "cached"
        else:
            data = fetch_ticker(ticker)
            if data is None:
                results[ticker] = "error"
            else:
                store.upsert(ticker, data)
                results[ticker] = "fetched"
        log.info("[%d/%d] %s: %s", i, total, ticker, results[ticker])
    return results
