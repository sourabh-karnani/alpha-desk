"""Headline retrieval via RSS (Google News). Optional dependency: feedparser."""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass


@dataclass
class NewsItem:
    title: str
    link: str
    published: str
    source: str
    summary: str = ""


def _require_feedparser():
    try:
        import feedparser  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "The 'news' extra is not installed. Run: uv sync --extra news"
        ) from exc
    return feedparser


def query_for_ticker(ticker: str) -> str:
    """Turn an exchange-suffixed ticker into a news search query.

    'RELIANCE.NS' -> 'RELIANCE stock', 'AAPL' -> 'AAPL stock'.
    """
    base = ticker.split(".")[0].replace("-", " ")
    return f"{base} stock"


def google_news_rss_url(query: str, lang: str = "en", region: str = "IN") -> str:
    q = urllib.parse.quote_plus(query)
    return (
        f"https://news.google.com/rss/search?q={q}"
        f"&hl={lang}-{region}&gl={region}&ceid={region}:{lang}"
    )


def fetch_headlines(
    ticker: str,
    limit: int = 8,
    lang: str = "en",
    region: str = "IN",
) -> list[NewsItem]:
    """Fetch up to `limit` recent headlines for `ticker`. Network call.

    Raises RuntimeError (not ImportError) if feedparser isn't installed, so
    callers can show a friendly message.
    """
    feedparser = _require_feedparser()
    url = google_news_rss_url(query_for_ticker(ticker), lang=lang, region=region)
    feed = feedparser.parse(url)
    items: list[NewsItem] = []
    for entry in feed.entries[:limit]:
        items.append(
            NewsItem(
                title=getattr(entry, "title", "").strip(),
                link=getattr(entry, "link", ""),
                published=getattr(entry, "published", ""),
                source=getattr(getattr(entry, "source", None), "title", "")
                if hasattr(entry, "source")
                else "",
                summary=getattr(entry, "summary", "")[:500],
            )
        )
    return items
