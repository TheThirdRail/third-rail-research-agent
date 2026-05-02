"""Story parser service.

Extracts structured story metadata from a description and optional
seed URL/RSS metadata. Outputs a StoryPacket for downstream use by
relevance scorer, balanced source planner, and source aggregator.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from src.core.config import settings
from src.core.llm_provider_docker import get_llm_router
from src.schemas.story_packet import StoryPacket
from src.services.semantic_query_expansion_service import (
    SemanticQueryExpansionService,
)

logger = logging.getLogger(__name__)


class StoryParserService:
    """Parse story descriptions into structured StoryPacket objects.

    Uses deterministic extraction first (entities, dates, URL parsing).
    Optional LLM query expansion can add semantic search phrases without
    changing the deterministic metadata gates.
    """

    def __init__(self, *, semantic_query_expansion_enabled: bool | None = None) -> None:
        self._semantic_query_expansion_override = semantic_query_expansion_enabled

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
        aliases = self._extract_aliases(actors, combined)
        verbs = self._extract_action_verbs(combined)
        quote_markers = self._extract_quote_markers(combined)
        number_markers = self._extract_number_markers(combined)
        platform_markers = self._extract_platform_markers(combined, seed_url)
        visual_descriptors = self._extract_visual_descriptors(combined)
        distinctive_terms = self._extract_distinctive_terms(
            quote_markers=quote_markers,
            number_markers=number_markers,
            platform_markers=platform_markers,
        )
        negative_clues = self._extract_negative_clues(combined)
        location = self._extract_location(combined)
        time_start, time_end = self._extract_time_window(combined)
        must_have = self._extract_must_have(
            headline,
            actors,
            verbs,
            distinctive_terms,
            visual_descriptors,
        )
        queries = self._build_query_pack(
            headline,
            actors,
            verbs,
            seed_url,
            distinctive_terms,
            visual_descriptors,
        )
        query_expander = SemanticQueryExpansionService()

        packet = StoryPacket(
            canonical_headline=headline,
            actors=actors,
            action_verbs=verbs,
            location=location,
            time_window_start=time_start,
            time_window_end=time_end,
            aliases=aliases,
            negative_clues=negative_clues,
            distinctive_terms=distinctive_terms,
            quote_markers=quote_markers,
            number_markers=number_markers,
            platform_markers=platform_markers,
            visual_descriptors=visual_descriptors,
            must_have_terms=must_have,
            must_not_have_terms=negative_clues,
            query_pack=queries,
            query_families={},
            disambiguation_notes="",
        )
        packet.query_families = query_expander.build_families(packet)
        packet.query_pack = self._dedupe_terms(
            packet.query_pack + query_expander.flatten(packet.query_families)
        )[:12]
        if self._semantic_query_expansion_enabled():
            self._expand_queries_with_llm(packet, description, rss_summary)

        logger.info(
            "Parsed story: headline=%r, actors=%d, queries=%d",
            headline[:60],
            len(actors),
            len(packet.query_pack),
        )
        return packet

    def _semantic_query_expansion_enabled(self) -> bool:
        if self._semantic_query_expansion_override is not None:
            return self._semantic_query_expansion_override
        value = getattr(settings, "semantic_query_expansion_enabled", False)
        return value if isinstance(value, bool) else False

    def _expand_queries_with_llm(
        self,
        packet: StoryPacket,
        description: str,
        rss_summary: str | None,
    ) -> None:
        """Append LLM-generated semantic queries, failing open on any issue."""
        try:
            router = get_llm_router(
                agent_name=getattr(
                    settings,
                    "semantic_query_expansion_agent_name",
                    "semantic_query_expander",
                )
            )
            raw = router.complete(
                self._semantic_query_messages(packet, description, rss_summary),
                temperature=0.1,
                max_tokens=500,
            )
            data = self._parse_llm_json(raw)
            max_queries = self._semantic_query_limit()
            queries = self._sanitize_semantic_queries(data.get("queries"), max_queries)
            aliases = self._sanitize_semantic_aliases(data.get("aliases"))
            if queries:
                semantic_queries = packet.query_families.setdefault(
                    "semantic_paraphrase",
                    [],
                )
                semantic_queries.extend(queries)
                packet.query_families["semantic_paraphrase"] = self._dedupe_terms(
                    semantic_queries
                )[:max_queries]
                expanded = SemanticQueryExpansionService().flatten(
                    packet.query_families
                )
                packet.query_pack = self._dedupe_terms(packet.query_pack + expanded)[
                    : 12 + max_queries
                ]
            if aliases:
                packet.aliases = self._dedupe_terms(packet.aliases + aliases)[:10]
        except Exception as exc:
            logger.warning("Semantic query expansion failed; using deterministic queries: %s", exc)

    def _semantic_query_messages(
        self,
        packet: StoryPacket,
        description: str,
        rss_summary: str | None,
    ) -> list[dict[str, str]]:
        system = (
            "Generate search phrases that help find articles about the same news "
            "event when outlets use different ideological framing. Return only "
            "valid JSON with keys queries and aliases. Do not include URLs."
        )
        user = "\n".join(
            [
                f"Canonical headline: {packet.canonical_headline}",
                f"Description: {description[:1200]}",
                f"RSS summary: {(rss_summary or '')[:800]}",
                f"Actors: {', '.join(packet.actors)}",
                f"Actions: {', '.join(packet.action_verbs)}",
                f"Distinctive terms: {', '.join(packet.distinctive_terms)}",
                f"Must-have terms: {', '.join(packet.must_have_terms)}",
                "",
                "Create short 3-9 word search queries for these frames:",
                "- neutral wire-service wording",
                "- conservative/right wording",
                "- progressive/left wording",
                "- procedural/legal wording",
                "",
                'Example output: {"queries":["Senate Republicans Cuba embargo vote"],"aliases":["Cuba embargo"]}',
            ]
        )
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    @staticmethod
    def _parse_llm_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        elif not text.startswith("{"):
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if not match:
                raise ValueError("semantic query model did not return JSON")
            text = match.group(1)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("semantic query model returned non-object JSON")
        return parsed

    def _semantic_query_limit(self) -> int:
        value = getattr(settings, "semantic_query_expansion_max_queries", 4)
        if not isinstance(value, int):
            return 4
        return max(0, min(value, 8))

    def _sanitize_semantic_queries(
        self,
        value: object,
        max_queries: int,
    ) -> list[str]:
        if not isinstance(value, list) or max_queries <= 0:
            return []
        sanitized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            query = self._clean_search_phrase(item)
            if not query:
                continue
            word_count = len(query.split())
            if 3 <= word_count <= 9:
                sanitized.append(query)
        return self._dedupe_terms(sanitized)[:max_queries]

    def _sanitize_semantic_aliases(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        aliases: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            alias = self._clean_search_phrase(item)
            if alias and 1 <= len(alias.split()) <= 5:
                aliases.append(alias)
        return self._dedupe_terms(aliases)[:6]

    @staticmethod
    def _clean_search_phrase(value: str) -> str:
        phrase = value.strip().strip("\"'")
        if not phrase or "://" in phrase or phrase.lower().startswith("www."):
            return ""
        phrase = re.sub(r"[\"'`]", "", phrase)
        phrase = re.sub(r"\s+", " ", phrase)
        return phrase.strip()

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

    def _extract_aliases(self, actors: list[str], text: str) -> list[str]:
        aliases: list[str] = []
        for actor in actors:
            parts = actor.split()
            if len(parts) >= 2:
                aliases.append(parts[-1])

        lower = text.lower()
        if "republican" in lower or "gop" in lower:
            aliases.extend(["GOP", "GOP senators", "Republicans"])
        if "democrat" in lower:
            aliases.extend(["Democrats", "Democratic lawmakers"])
        if "donald trump" in lower or "trump" in lower:
            aliases.extend(["Trump", "Donald Trump"])
        if "james comey" in lower or "comey" in lower:
            aliases.extend(["Comey", "James Comey"])
        return self._dedupe_terms(aliases)[:10]

    @staticmethod
    def _extract_quote_markers(text: str) -> list[str]:
        markers = re.findall(r"[\"']([^\"']{2,80})[\"']", text)
        return StoryParserService._dedupe_terms(
            [marker.strip() for marker in markers if marker.strip()]
        )[:8]

    @staticmethod
    def _extract_number_markers(text: str) -> list[str]:
        markers = re.findall(r"\b[A-Z]*\d[A-Z0-9-]{1,11}\b", text)
        return StoryParserService._dedupe_terms(markers)[:8]

    @staticmethod
    def _extract_platform_markers(text: str, seed_url: str | None) -> list[str]:
        markers: list[str] = []
        platforms = {
            "X": r"\bX\b|\bTwitter\b|\bx\.com\b|\btwitter\.com\b",
            "Instagram": r"\bInstagram\b|\binstagram\.com\b",
            "Threads": r"\bThreads\b|\bthreads\.net\b",
            "Facebook": r"\bFacebook\b|\bfacebook\.com\b",
            "TikTok": r"\bTikTok\b|\btiktok\.com\b",
            "Truth Social": r"\bTruth\s+Social\b|\btruthsocial\.com\b",
        }
        searchable = text
        if seed_url:
            searchable = f"{searchable} {seed_url}"
        for label, pattern in platforms.items():
            if re.search(pattern, searchable, re.IGNORECASE):
                markers.append(label)
        return StoryParserService._dedupe_terms(markers)[:6]

    def _extract_distinctive_terms(
        self,
        *,
        quote_markers: list[str] | None = None,
        number_markers: list[str] | None = None,
        platform_markers: list[str] | None = None,
    ) -> list[str]:
        """Extract distinctive tokens that should constrain retrieval."""
        terms: list[str] = []
        terms.extend(quote_markers or [])
        terms.extend(number_markers or [])
        terms.extend(platform_markers or [])
        return self._dedupe_terms(terms)[:8]

    @staticmethod
    def _extract_negative_clues(text: str) -> list[str]:
        clues: list[str] = []
        patterns = [
            r"\bnot\s+(?:about|involving|related to)\s+([^.;,]{3,80})",
            r"\bnot\s+([^.;,]{3,80})",
            r"\bmust\s+not\s+(?:include|mention|match)\s+([^.;,]{3,80})",
            r"\bexclude\s+([^.;,]{3,80})",
            r"\bunrelated\s+(?:to|case|story)?\s*([^.;,]{3,80})",
        ]
        for pattern in patterns:
            clues.extend(re.findall(pattern, text, flags=re.IGNORECASE))
        cleaned = []
        for clue in clues:
            clue = re.sub(r"\s+", " ", clue).strip(" -:()[]\"'")
            words = clue.split()
            if words:
                cleaned.append(" ".join(words[:6]))
        return StoryParserService._dedupe_terms(cleaned)[:6]

    def _extract_visual_descriptors(self, text: str) -> list[str]:
        descriptors = [
            "photo",
            "image",
            "picture",
            "screenshot",
            "seashell",
            "seashells",
            "shells",
            "post",
            "social post",
            "caption",
            "number",
            "symbols",
        ]
        found = [
            descriptor
            for descriptor in descriptors
            if re.search(rf"\b{re.escape(descriptor)}\b", text, re.IGNORECASE)
        ]
        return self._dedupe_terms(found)[:6]

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
                            return (
                                parsed - timedelta(days=3),
                                parsed + timedelta(days=3),
                            )
                        except ValueError:
                            continue
                except Exception:
                    continue

        # Default: ±7 days from now
        return (now - timedelta(days=7), now + timedelta(days=1))

    def _extract_must_have(
        self,
        _headline: str,
        actors: list[str],
        verbs: list[str],
        distinctive_terms: list[str],
        visual_descriptors: list[str],
    ) -> list[str]:
        """Build must-have terms from key story elements."""
        terms: list[str] = []
        # Add first actor name if available
        if actors:
            terms.append(actors[0])
        # Add key verb if available
        if verbs:
            terms.append(verbs[0])
        terms.extend(distinctive_terms[:4])
        terms.extend(visual_descriptors[:3])
        return self._dedupe_terms(terms)[:10]

    def _build_query_pack(
        self,
        headline: str,
        actors: list[str],
        verbs: list[str],
        seed_url: str | None,
        distinctive_terms: list[str] | None = None,
        visual_descriptors: list[str] | None = None,
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

        if actors and distinctive_terms:
            queries.append(f"{actors[0]} {' '.join(distinctive_terms[:3])}")

        if distinctive_terms and visual_descriptors:
            queries.append(" ".join(distinctive_terms[:3] + visual_descriptors[:2]))

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
    def _dedupe_terms(terms: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for term in terms:
            normalized = term.strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            ordered.append(normalized)
        return ordered

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
