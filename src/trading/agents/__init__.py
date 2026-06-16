"""LLM news / event agents.

Two optional capabilities, both degrading gracefully when their dependency is
absent (the package imports fine without `feedparser` or `anthropic`):

* `news`      — pull recent headlines for a ticker (RSS via `feedparser`).
* `sentiment` — have a Claude model read those headlines and return a structured
                bullish/neutral/bearish assessment with extracted events.

Network and API calls only happen when you call the functions, never at import.
"""
from trading.agents.news import NewsItem, fetch_headlines
from trading.agents.sentiment import (
    NewsAssessment,
    assess_ticker,
    build_prompt,
    parse_assessment,
)

__all__ = [
    "NewsItem",
    "fetch_headlines",
    "NewsAssessment",
    "assess_ticker",
    "build_prompt",
    "parse_assessment",
]
