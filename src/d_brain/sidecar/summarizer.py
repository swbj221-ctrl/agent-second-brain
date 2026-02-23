"""Local utility summarizer for short summaries."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SummaryResult


def normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace."""
    return " ".join(text.split()).strip()


@dataclass(slots=True)
class HeuristicSummarizer:
    """Simple heuristic summarizer for Stage 2."""

    max_chars: int = 400
    model_ref: str = "utility:heuristic"

    def summarize(self, text: str, summary_format: str = "plain") -> SummaryResult:
        cleaned = normalize_text(text)
        if len(cleaned) <= self.max_chars:
            summary = cleaned
        else:
            summary = cleaned[: self.max_chars].rstrip()
            if not summary.endswith("."):
                summary = f"{summary}..."
        return SummaryResult(
            summary_text=summary,
            summary_format=summary_format,
            model_ref=self.model_ref,
        )
