from __future__ import annotations

import importlib.util

import pytest

from trading.agents.news import NewsItem, google_news_rss_url, query_for_ticker
from trading.agents.sentiment import DEFAULT_MODEL, build_prompt, parse_assessment

_HAS_FEEDPARSER = importlib.util.find_spec("feedparser") is not None
_HAS_ANTHROPIC = importlib.util.find_spec("anthropic") is not None


def test_query_and_url():
    assert query_for_ticker("RELIANCE.NS") == "RELIANCE stock"
    assert query_for_ticker("BRK-B") == "BRK B stock"
    url = google_news_rss_url("AAPL stock", region="US")
    assert url.startswith("https://news.google.com/rss/search?q=AAPL")
    assert "gl=US" in url


def test_build_prompt_includes_headlines():
    items = [NewsItem("Reliance Q4 beats estimates", "u", "p", "ET"),
             NewsItem("New refinery announced", "u", "p", "")]
    prompt = build_prompt("RELIANCE.NS", items)
    assert "RELIANCE.NS" in prompt
    assert "Reliance Q4 beats estimates (ET)" in prompt


def test_parse_clean_json():
    text = (
        '{"sentiment":"bullish","score":0.6,"confidence":0.8,'
        '"summary":"Good.","events":["Q4 beat"]}'
    )
    a = parse_assessment(text, "X", 3, DEFAULT_MODEL)
    assert a.sentiment == "bullish"
    assert a.score == 0.6 and a.confidence == 0.8
    assert a.events == ["Q4 beat"] and a.n_headlines == 3


def test_parse_json_with_surrounding_prose():
    text = (
        'Here is the JSON:\n'
        '{"sentiment":"bearish","score":-2,"summary":"Bad"}\nThanks!'
    )
    a = parse_assessment(text, "X", 0, DEFAULT_MODEL)
    assert a.sentiment == "bearish"
    assert a.score == -1.0  # clamped into [-1, 1]


def test_parse_garbage_defaults_to_neutral():
    a = parse_assessment("not json at all", "X", 0, DEFAULT_MODEL)
    assert a.sentiment == "neutral"
    assert a.score == 0.0 and a.events == []


@pytest.mark.skipif(_HAS_FEEDPARSER, reason="feedparser installed; degrade path not exercised")
def test_fetch_headlines_without_feedparser_raises_runtimeerror():
    from trading.agents.news import fetch_headlines

    with pytest.raises(RuntimeError, match="news"):
        fetch_headlines("AAPL")


@pytest.mark.skipif(_HAS_ANTHROPIC, reason="anthropic installed; degrade path not exercised")
def test_assess_without_anthropic_raises_runtimeerror():
    from trading.agents.sentiment import assess_ticker

    with pytest.raises(RuntimeError, match="news"):
        assess_ticker("AAPL", [])
