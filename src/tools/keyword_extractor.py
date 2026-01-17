"""Keyword Extraction Tool for CrewAI."""

import logging
from dataclasses import dataclass

from crewai_tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class Keyword:
    """Extracted keyword with score."""

    term: str
    score: float


class KeywordExtractor:
    """Extracts keywords from text using YAKE."""

    def __init__(
        self,
        language: str = "en",
        max_ngram_size: int = 2,
        deduplication_threshold: float = 0.9,
    ):
        """Initialize extractor."""
        self.language = language
        self.max_ngram_size = max_ngram_size
        self.dedup_threshold = deduplication_threshold
        self._extractor = None

    def _get_extractor(self):
        """Lazy load YAKE extractor."""
        if self._extractor is None:
            try:
                import yake

                self._extractor = yake.KeywordExtractor(
                    lan=self.language,
                    n=self.max_ngram_size,
                    dedupLim=self.dedup_threshold,
                    top=20,
                    features=None,
                )
            except ImportError:
                logger.error("YAKE not installed. Install with: pip install yake")
                raise
        return self._extractor

    def extract(self, text: str, top_n: int = 10) -> list[Keyword]:
        """Extract keywords from text.

        Args:
            text: Text to extract keywords from
            top_n: Number of keywords to return

        Returns:
            List of Keyword objects sorted by relevance
        """
        if not text or len(text) < 20:
            return []

        try:
            extractor = self._get_extractor()
            keywords = extractor.extract_keywords(text)

            # YAKE returns (keyword, score) where lower score = more important
            # Invert scores so higher = more important
            results = []
            for kw, score in keywords[:top_n]:
                # Invert and normalize score (YAKE scores are typically 0-1)
                inverted = 1.0 - min(score, 1.0)
                results.append(Keyword(term=kw, score=inverted))

            return sorted(results, key=lambda x: x.score, reverse=True)

        except Exception as e:
            logger.error(f"Keyword extraction failed: {e}")
            return []


class KeywordExtractorTool(BaseTool):
    """CrewAI tool for keyword extraction."""

    name: str = "Keyword Extractor"
    description: str = """Extracts the most important keywords and phrases from text.
    Useful for identifying main topics, themes, and entities in an article.
    Returns ranked keywords with relevance scores."""

    def _run(
        self,
        text: str,
        top_n: int = 10,
    ) -> str:
        """Execute keyword extraction.

        Args:
            text: Text to extract keywords from
            top_n: Number of top keywords to return (1-20)

        Returns:
            Formatted list of keywords with scores
        """
        top_n = min(max(1, top_n), 20)  # Clamp to 1-20

        if not text or len(text) < 50:
            return "Text too short for keyword extraction (need at least 50 characters)."

        extractor = KeywordExtractor()
        keywords = extractor.extract(text, top_n)

        if not keywords:
            return "No keywords could be extracted from the text."

        # Format output
        output_lines = [f"Top {len(keywords)} Keywords:\n"]

        for i, kw in enumerate(keywords, 1):
            bar = "█" * int(kw.score * 10)
            output_lines.append(f"{i:2}. {kw.term:<30} {bar} ({kw.score:.2f})\n")

        return "".join(output_lines)


class TopicMatcherTool(BaseTool):
    """CrewAI tool for matching text against topic keywords."""

    name: str = "Topic Matcher"
    description: str = """Checks how well a text matches a set of topic keywords.
    Provide text and comma-separated topic keywords.
    Returns a relevance score and matched keywords."""

    def _run(
        self,
        text: str,
        topic_keywords: str,
    ) -> str:
        """Match text against topic keywords.

        Args:
            text: Text to analyze
            topic_keywords: Comma-separated keywords to match

        Returns:
            Match results with relevance score
        """
        if not text or not topic_keywords:
            return "Both text and topic_keywords are required."

        # Parse keywords
        keywords = [k.strip().lower() for k in topic_keywords.split(",") if k.strip()]
        text_lower = text.lower()

        # Check for matches
        matches = []
        for kw in keywords:
            if kw in text_lower:
                count = text_lower.count(kw)
                matches.append((kw, count))

        if not matches:
            return f"No matches found for keywords: {', '.join(keywords)}"

        # Calculate relevance score
        total_matches = sum(count for _, count in matches)
        match_ratio = len(matches) / len(keywords)
        relevance = min(1.0, match_ratio + (total_matches / 100))

        # Format output
        output_lines = [
            f"=== TOPIC MATCH RESULTS ===\n",
            f"Keywords checked: {len(keywords)}\n",
            f"Keywords found: {len(matches)}\n",
            f"Relevance Score: {relevance:.2f}\n\n",
            "Matched Keywords:\n",
        ]

        for kw, count in sorted(matches, key=lambda x: x[1], reverse=True):
            output_lines.append(f"  • {kw} (found {count} times)\n")

        return "".join(output_lines)
