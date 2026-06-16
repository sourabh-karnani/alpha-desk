"""Paper-book execution: turn recommendations into tracked paper positions and
mark them against subsequent bars to score how the ideas actually played out."""
from trading.execution.paper_book import (
    PaperBook,
    open_recommendations,
    summarize,
    update_positions,
)

__all__ = ["PaperBook", "open_recommendations", "summarize", "update_positions"]
