"""LLM news assessment via the Claude API. Optional dependency: anthropic.

`build_prompt` and `parse_assessment` are pure (no network, no SDK) so the
prompt construction and response handling are unit-testable; `assess_ticker`
wires them to a real API call.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from trading.agents.news import NewsItem

# Cheap + fast model for headline summarisation; override via assess_ticker(model=).
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are an equity news analyst. Given recent headlines for one stock, judge "
    "the near-term directional bias for the share price. Be skeptical of hype and "
    "of headline-only information. Respond with STRICT JSON only, no prose, using "
    "this schema: {\"sentiment\": \"bullish|neutral|bearish\", \"score\": number "
    "in [-1,1], \"confidence\": number in [0,1], \"summary\": string (<=2 "
    "sentences), \"events\": array of short strings for concrete catalysts "
    "(earnings, M&A, guidance, regulatory, management change)}."
)

_VALID_SENTIMENT = {"bullish", "neutral", "bearish"}


@dataclass
class NewsAssessment:
    ticker: str
    sentiment: str
    score: float
    confidence: float
    summary: str
    events: list[str] = field(default_factory=list)
    n_headlines: int = 0
    model: str = DEFAULT_MODEL


def build_prompt(ticker: str, headlines: list[NewsItem]) -> str:
    lines = [f"Stock: {ticker}", "", "Recent headlines:"]
    for i, h in enumerate(headlines, 1):
        src = f" ({h.source})" if h.source else ""
        lines.append(f"{i}. {h.title}{src}")
    if not headlines:
        lines.append("(no headlines found)")
    lines += ["", "Return the JSON assessment now."]
    return "\n".join(lines)


def _clamp(x, lo, hi, default=0.0):
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return default


def parse_assessment(text: str, ticker: str, n_headlines: int, model: str) -> NewsAssessment:
    """Parse a model response into a NewsAssessment, tolerating stray prose."""
    data: dict = {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        m = re.search(r"\{.*\}", text or "", re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
            except json.JSONDecodeError:
                data = {}

    sentiment = str(data.get("sentiment", "neutral")).lower()
    if sentiment not in _VALID_SENTIMENT:
        sentiment = "neutral"
    events = data.get("events") or []
    if not isinstance(events, list):
        events = [str(events)]

    return NewsAssessment(
        ticker=ticker,
        sentiment=sentiment,
        score=_clamp(data.get("score", 0.0), -1.0, 1.0),
        confidence=_clamp(data.get("confidence", 0.0), 0.0, 1.0),
        summary=str(data.get("summary", "")).strip(),
        events=[str(e) for e in events][:8],
        n_headlines=n_headlines,
        model=model,
    )


def _require_anthropic():
    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "The 'news' extra is not installed. Run: uv sync --extra news"
        ) from exc
    return anthropic


def assess_ticker(
    ticker: str,
    headlines: list[NewsItem],
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_tokens: int = 400,
) -> NewsAssessment:
    """Call Claude to assess `headlines` for `ticker`. Network call.

    The system prompt is marked for prompt caching so repeated calls across a
    universe reuse the cached prefix.
    """
    anthropic = _require_anthropic()
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot run the news LLM agent.")

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": build_prompt(ticker, headlines)}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    return parse_assessment(text, ticker, len(headlines), model)
