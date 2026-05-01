"""Deterministic query-family expansion for story retrieval."""

from __future__ import annotations

from src.schemas.story_packet import StoryPacket


class SemanticQueryExpansionService:
    """Build query families without changing relevance gates."""

    FAMILY_ORDER = (
        "lexical",
        "semantic_paraphrase",
        "opposing_frame",
        "visual_social",
    )

    def build_families(self, packet: StoryPacket) -> dict[str, list[str]]:
        """Return grouped search queries for bucket-lane probing."""
        families = {
            "lexical": self._lexical_queries(packet),
            "semantic_paraphrase": self._semantic_paraphrases(packet),
            "opposing_frame": self._opposing_frame_queries(packet),
            "visual_social": self._visual_social_queries(packet),
        }
        return {
            family: self._dedupe(queries)
            for family, queries in families.items()
            if queries
        }

    def flatten(self, families: dict[str, list[str]]) -> list[str]:
        """Flatten query families in stable retrieval order."""
        queries: list[str] = []
        for family in self.FAMILY_ORDER:
            queries.extend(families.get(family, []))
        for family, values in families.items():
            if family not in self.FAMILY_ORDER:
                queries.extend(values)
        return self._dedupe(queries)

    def _lexical_queries(self, packet: StoryPacket) -> list[str]:
        queries: list[str] = []
        if packet.canonical_headline:
            queries.append(packet.canonical_headline)
        if packet.actors and packet.action_verbs:
            queries.append(f"{packet.actors[0]} {packet.action_verbs[0]}")
        if packet.actors and packet.distinctive_terms:
            queries.append(
                f"{packet.actors[0]} {' '.join(packet.distinctive_terms[:3])}"
            )
        return queries

    def _semantic_paraphrases(self, packet: StoryPacket) -> list[str]:
        queries: list[str] = []
        actor = packet.aliases[0] if packet.aliases else (
            packet.actors[0] if packet.actors else ""
        )
        markers = " ".join(packet.distinctive_terms[:2])
        if actor and markers:
            queries.append(f"{actor} story {markers}")
        if actor and packet.action_verbs:
            queries.append(f"{actor} {packet.action_verbs[0]} latest")
        return queries

    def _opposing_frame_queries(self, packet: StoryPacket) -> list[str]:
        queries: list[str] = []
        combined_terms = " ".join(
            (packet.actors[:1] or packet.aliases[:1])
            + packet.distinctive_terms[:2]
        ).strip()
        if not combined_terms:
            return []
        queries.append(f"{combined_terms} conservative reaction")
        queries.append(f"{combined_terms} progressive reaction")
        return queries

    def _visual_social_queries(self, packet: StoryPacket) -> list[str]:
        queries: list[str] = []
        markers = packet.number_markers + packet.quote_markers + packet.platform_markers
        visual = packet.visual_descriptors[:2]
        actor = packet.actors[0] if packet.actors else ""
        if actor and markers:
            queries.append(f"{actor} {' '.join(markers[:2])}")
        if markers and visual:
            queries.append(" ".join(markers[:2] + visual))
        return queries

    @staticmethod
    def _dedupe(queries: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for query in queries:
            normalized = " ".join(query.split()).strip()
            key = normalized.lower()
            if not normalized or key in seen:
                continue
            seen.add(key)
            ordered.append(normalized)
        return ordered
