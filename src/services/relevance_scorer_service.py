"""Relevance scorer service.

Scores candidate articles/stories on multi-factor relevance
against a parsed story packet. Hybrid deterministic + model stage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from src.schemas.story_packet import StoryPacket

logger = logging.getLogger(__name__)


@dataclass
class RelevanceScore:
    """Relevance score breakdown for a candidate article."""

    total: float
    entity_overlap: float
    event_overlap: float
    time_overlap: float
    place_overlap: float
    topic_match: float
    novelty: float
    coverage_type: str
    rejection_reason: str | None


class RelevanceScorerService:
    """Score candidate stories/articles against a StoryPacket."""

    REJECTION_THRESHOLD = 0.35

    def score(
        self,
        candidate_title: str,
        candidate_text: str,
        candidate_date: datetime | None,
        story_packet: StoryPacket,
        *,
        seen_domains: set[str] | None = None,
        candidate_domain: str = "",
    ) -> RelevanceScore:
        """Score a candidate against the story packet."""
        combined = f"{candidate_title} {candidate_text[:2000]}".lower()

        entity_score = self._entity_overlap(combined, story_packet)
        event_score = self._event_overlap(combined, story_packet)
        time_score = self._time_overlap(candidate_date, story_packet)
        place_score = self._place_overlap(combined, story_packet)
        topic_score = self._topic_match(combined, story_packet)
        novelty_score = self._novelty(candidate_domain, seen_domains)
        coverage_type = self._classify_coverage_type(
            combined,
            entity_score,
            event_score,
            topic_score,
            story_packet,
        )

        total = (
            entity_score * 0.30
            + event_score * 0.25
            + time_score * 0.15
            + place_score * 0.10
            + topic_score * 0.10
            + novelty_score * 0.10
        )

        rejection = self._check_rejection(
            total,
            entity_score,
            event_score,
            topic_score,
            coverage_type,
            combined,
            story_packet,
        )

        return RelevanceScore(
            total=total,
            entity_overlap=entity_score,
            event_overlap=event_score,
            time_overlap=time_score,
            place_overlap=place_score,
            topic_match=topic_score,
            novelty=novelty_score,
            coverage_type=coverage_type,
            rejection_reason=rejection,
        )

    def _entity_overlap(self, text: str, packet: StoryPacket) -> float:
        if not packet.actors:
            return 0.5
        matches = sum(1 for a in packet.actors if self._term_in_text(a, text))
        return min(1.0, matches / max(1, len(packet.actors)))

    def _event_overlap(self, text: str, packet: StoryPacket) -> float:
        if not packet.action_verbs:
            return 0.5
        matches = sum(1 for v in packet.action_verbs if self._term_in_text(v, text))
        return min(1.0, matches / max(1, len(packet.action_verbs)))

    def _time_overlap(self, date: datetime | None, packet: StoryPacket) -> float:
        if not date or not packet.time_window_start or not packet.time_window_end:
            return 0.5
        if packet.time_window_start <= date <= packet.time_window_end:
            return 1.0
        # Penalize by distance from window

        window_size = (packet.time_window_end - packet.time_window_start).days or 7
        if date < packet.time_window_start:
            gap = (packet.time_window_start - date).days
        else:
            gap = (date - packet.time_window_end).days
        return max(0.0, 1.0 - (gap / max(1, window_size * 2)))

    def _place_overlap(self, text: str, packet: StoryPacket) -> float:
        if not packet.location:
            return 0.5
        return 1.0 if packet.location.lower() in text else 0.2

    def _topic_match(self, text: str, packet: StoryPacket) -> float:
        if not packet.must_have_terms:
            return 0.5
        matches = sum(1 for t in packet.must_have_terms if self._term_in_text(t, text))
        return min(1.0, matches / max(1, len(packet.must_have_terms)))

    def _novelty(self, domain: str, seen: set[str] | None) -> float:
        if not seen or not domain:
            return 1.0
        return 0.2 if domain in seen else 1.0

    def _check_rejection(
        self,
        total: float,
        entity: float,
        event: float,
        topic: float,
        coverage_type: str,
        text: str,
        packet: StoryPacket,
    ) -> str | None:
        if coverage_type != "direct":
            return f"coverage_type_not_direct: {coverage_type}"
        if packet.actors and packet.action_verbs and entity < 0.1 and event < 0.1:
            return "same_topic_wrong_entities_and_event"
        if packet.must_have_terms and topic < 0.35:
            return "missing_core_event_markers"
        if total < self.REJECTION_THRESHOLD:
            if entity < 0.1:
                return "same_topic_wrong_entities"
            if event < 0.1:
                return "same_person_wrong_event"
            return "low_overall_relevance"
        # Check must-not-have terms
        for term in packet.must_not_have_terms:
            if self._term_in_text(term, text):
                return f"contains_disambiguation_exclusion: {term}"
        return None

    def _classify_coverage_type(
        self,
        text: str,
        entity: float,
        event: float,
        topic: float,
        packet: StoryPacket,
    ) -> str:
        opinion_markers = ("opinion", "editorial", "analysis:", "column:")
        if any(marker in text[:300] for marker in opinion_markers):
            return "opinion"

        distinctive_hits = sum(
            1
            for term in packet.distinctive_terms + packet.visual_descriptors
            if self._term_in_text(term, text)
        )
        has_distinctive = distinctive_hits > 0 or not (
            packet.distinctive_terms or packet.visual_descriptors
        )

        if entity >= 0.5 and (event >= 0.5 or topic >= 0.5) and has_distinctive:
            return "direct"
        if entity >= 0.5:
            return "contextual"
        if entity > 0:
            return "mention"
        return "mention"

    @staticmethod
    def _term_in_text(term: str, text: str) -> bool:
        lowered = term.lower().strip()
        if not lowered:
            return False
        if lowered in text:
            return True
        variants = {
            lowered.rstrip("s"),
            lowered + "s",
            lowered + "ed",
            lowered.rstrip("e") + "ed",
            lowered.rstrip("s") + "ed",
        }
        return any(variant and variant in text for variant in variants)
