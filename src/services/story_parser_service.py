"""Story parser service.

Extracts structured story metadata from a description and optional
seed URL/RSS metadata. Outputs a StoryPacket for downstream use by
relevance scorer, balanced source planner, and source aggregator.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from src.schemas.story_packet import StoryPacket

logger = logging.getLogger(__name__)


class StoryParserService:
    """Parse story descriptions into structured StoryPacket objects.

    Uses deterministic extraction first (entities, dates, URL parsing).
    LLM stage can be added later for ambiguity resolution.
    """

    def parse(
        self,
        description: str,
        seed_url: str | None = None,
        rss_title: str | None = None,
        rss_summary: str | None = None,
    ) -> StoryPacket:
        """Parse a story description into a structured packet.

        Args:
            description: Story description text.
            seed_url: Optional seed article URL.
            rss_title: Optional RSS-matched headline.
            rss_summary: Optional RSS-matched summary.

        Returns:
            StoryPacket with extracted metadata.
        """
        # Combine all text sources for extraction
        combined = description
        if rss_title:
            combined = f"{rss_title}. {combined}"
        if rss_summary:
            combined = f"{combined} {rss_summary}"

        headline = rss_title or self._extract_headline(description)
        actors = self._extract_actors(combined)
        verbs = self._extract_action_verbs(combined)
        location = self._extract_location(combined)
        time_start, time_end = self._extract_time_window(combined)
        must_have = self._extract_must_have(headline, actors, verbs)
        queries = self._build_query_pack(headline, actors, verbs, seed_url)

        packet = StoryPacket(
            canonical_headline=headline,
            actors=actors,
            action_verbs=verbs,
            location=location,
            time_window_start=time_start,
            time_window_end=time_end,
            aliases=[],
            must_have_terms=must_have,
            must_not_have_terms=[],
            query_pack=queries,
            disambiguation_notes="",
        )

        logger.info("Parsed story: headline=%r, actors=%d, queries=%d",
                     headline[:60], len(actors), len(queries))
        return packet

    def _extract_headline(self, description: str) -> str:
        """Extract or generate a canonical headline from description."""
        # Use first sentence as headline candidate
        sentences = re.split(r"[.!?]\s+", description.strip())
        if sentences:
            headline = sentences[0].strip()
            if len(headline) > 200:
                headline = headline[:197] + "..."
            return headline
        return description[:200]

    def _extract_actors(self, text: str) -> list[str]:
        """Extract named entities (people/orgs) from text.

        Uses capitalization heuristics. A proper NER model can
        replace this for higher accuracy.
        """
        # Find capitalized multi-word sequences (likely names/orgs)
        pattern = r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
        matches = re.findall(pattern, text)
        # Deduplicate preserving order
        seen: set[str] = set()
        actors: list[str] = []
        for match in matches:
            normalized = match.strip()
            if normalized not in seen and len(normalized) > 3:
                seen.add(normalized)
                actors.append(normalized)
        return actors[:10]

    def _extract_action_verbs(self, text: str) -> list[str]:
        """Extract key action verbs from the text."""
        # Common news action verbs
        action_patterns = [
            r"\b(signed|vetoed|proposed|announced|arrested|charged|indicted)\b",
            r"\b(resigned|fired|appointed|nominated|elected|defeated)\b",
            r"\b(passed|blocked|rejected|approved|overturned|reversed)\b",
            r"\b(investigated|sued|filed|settled|convicted|acquitted)\b",
            r"\b(attacked|invaded|withdrew|deployed|sanctioned|banned)\b",
            r"\b(collapsed|crashed|surged|plummeted|recovered|grew)\b",
        ]
        verbs: list[str] = []
        for pattern in action_patterns:
            found = re.findall(pattern, text.lower())
            verbs.extend(found)
        return list(dict.fromkeys(verbs))[:5]

    def _extract_location(self, text: str) -> str:
        """Extract primary geographic location if mentioned."""
        # Look for common location patterns
        loc_pattern = r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:,\s*[A-Z]{2})?)\b"
        matches = re.findall(loc_pattern, text)
        return matches[0] if matches else ""

    def _extract_time_window(
        self, text: str
    ) -> tuple[datetime | None, datetime | None]:
        """Extract or infer a time window for the story."""
        now = datetime.now(tz=None)

        # Look for explicit date patterns
        date_pattern = r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b"
        matches = re.findall(date_pattern, text)
        if matches:
            for match in matches:
                try:
                    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y"):
                        try:
                            parsed = datetime.strptime(match, fmt)
                            return (parsed - timedelta(days=3), parsed + timedelta(days=3))
                        except ValueError:
                            continue
                except Exception:
                    continue

        # Default: ±7 days from now
        return (now - timedelta(days=7), now + timedelta(days=1))

    def _extract_must_have(
        self, headline: str, actors: list[str], verbs: list[str]
    ) -> list[str]:
        """Build must-have terms from key story elements."""
        terms: list[str] = []
        # Add first actor name if available
        if actors:
            terms.append(actors[0])
        # Add key verb if available
        if verbs:
            terms.append(verbs[0])
        return terms

    def _build_query_pack(
        self,
        headline: str,
        actors: list[str],
        verbs: list[str],
        seed_url: str | None,
    ) -> list[str]:
        """Build pre-formatted search queries."""
        queries: list[str] = []

        # Primary: headline-based query
        if headline:
            # Clean headline for search
            clean = re.sub(r"[^\w\s]", "", headline)
            words = clean.split()
            if len(words) > 8:
                clean = " ".join(words[:8])
            queries.append(clean)

        # Actor + verb query
        if actors and verbs:
            queries.append(f"{actors[0]} {verbs[0]}")

        # Actor-only query
        if actors and len(actors) > 1:
            queries.append(f"{actors[0]} {actors[1]}")

        # URL slug keywords
        if seed_url:
            slug_terms = self._slug_keywords(seed_url)
            if slug_terms:
                queries.append(slug_terms)

        return queries[:4]

    @staticmethod
    def _slug_keywords(url: str) -> str:
        """Extract keywords from URL path slug."""
        try:
            path = urlparse(url).path
            slug = path.rstrip("/").rsplit("/", 1)[-1]
            words = re.sub(r"[-_]", " ", slug).split()
            # Filter noise
            words = [w for w in words if len(w) > 2 and not w.isdigit()]
            return " ".join(words[:6])
        except Exception:
            return ""
