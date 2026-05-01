"""In-memory semantic similarity for pre-retention source candidates."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from src.core.embedding_provider import EmbeddingProvider, get_embedding_provider
from src.schemas.story_packet import StoryPacket

CANDIDATE_TEXT_CHARS = 4000
CANDIDATE_CHUNK_CHARS = 700
CANDIDATE_CHUNK_STRIDE = 500


@dataclass(frozen=True)
class CandidateSemanticSeed:
    """Temporary seed vector used before a persistent Story row exists."""

    run_id: str
    text: str
    vector: list[float]


@dataclass(frozen=True)
class CandidateSemanticScores:
    """Semantic similarity breakdown for a pre-retention candidate."""

    aggregate_similarity: float
    title_similarity: float | None = None
    lede_similarity: float | None = None
    chunk_similarity: float | None = None


class CandidateSemanticScorer:
    """Score candidates against an in-memory seed story vector."""

    def __init__(
        self,
        story_packet: StoryPacket,
        seed_text: str,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider or get_embedding_provider()
        seed_block = self._seed_text(story_packet, seed_text)
        seed_vector = self._embedding_provider.embed_texts([seed_block])[0]
        title_seed = self._title_seed_text(story_packet)
        self._title_seed_vector = self._embedding_provider.embed_texts([title_seed])[0]
        self.seed = CandidateSemanticSeed(
            run_id=hashlib.sha256(seed_block.encode("utf-8")).hexdigest(),
            text=seed_block,
            vector=seed_vector,
        )

    def score_candidate(self, candidate_title: str, candidate_text: str) -> float:
        """Return cosine similarity between the seed story and a candidate."""
        return self.score_candidate_diagnostics(
            candidate_title,
            candidate_text,
        ).aggregate_similarity

    def score_candidate_diagnostics(
        self,
        candidate_title: str,
        candidate_text: str,
    ) -> CandidateSemanticScores:
        """Return aggregate, title, and lede semantic similarity."""
        candidate_block = self._candidate_text(candidate_title, candidate_text)
        title_block = candidate_title.strip()
        lede_block = self._lede_text(candidate_text)
        chunks = self._chunk_text(candidate_text)
        vectors = self._embedding_provider.embed_texts(
            [candidate_block, title_block, lede_block, *chunks]
        )
        chunk_vectors = vectors[3:]
        chunk_similarity = (
            max(
                self._cosine_similarity(self.seed.vector, vector)
                for vector in chunk_vectors
            )
            if chunk_vectors
            else None
        )
        full_similarity = self._cosine_similarity(self.seed.vector, vectors[0])
        return CandidateSemanticScores(
            aggregate_similarity=max(
                full_similarity,
                chunk_similarity if chunk_similarity is not None else 0.0,
            ),
            title_similarity=self._cosine_similarity(
                self._title_seed_vector,
                vectors[1],
            )
            if title_block
            else None,
            lede_similarity=self._cosine_similarity(self.seed.vector, vectors[2])
            if lede_block
            else None,
            chunk_similarity=chunk_similarity,
        )

    @classmethod
    def _seed_text(cls, story_packet: StoryPacket, seed_text: str) -> str:
        parts = [
            f"Canonical headline: {story_packet.canonical_headline}",
            f"User description: {seed_text}",
            cls._term_line("Actors", story_packet.actors),
            cls._term_line("Aliases", story_packet.aliases),
            cls._term_line("Actions", story_packet.action_verbs),
            cls._term_line("Distinctive terms", story_packet.distinctive_terms),
            cls._term_line("Visual descriptors", story_packet.visual_descriptors),
            cls._term_line("Must-have terms", story_packet.must_have_terms),
            cls._term_line("Must-not-have terms", story_packet.must_not_have_terms),
            f"Disambiguation notes: {story_packet.disambiguation_notes}",
        ]
        return "\n".join(part for part in parts if part.strip())

    @staticmethod
    def _candidate_text(candidate_title: str, candidate_text: str) -> str:
        body = " ".join(candidate_text.split())
        return f"Title: {candidate_title.strip()}\nText: {body[:CANDIDATE_TEXT_CHARS]}"

    @classmethod
    def _title_seed_text(cls, story_packet: StoryPacket) -> str:
        return "\n".join(
            part
            for part in [
                story_packet.canonical_headline,
                cls._term_line("Actors", story_packet.actors),
                cls._term_line("Aliases", story_packet.aliases),
                cls._term_line("Distinctive terms", story_packet.distinctive_terms),
            ]
            if part.strip()
        )

    @staticmethod
    def _lede_text(candidate_text: str) -> str:
        return " ".join(candidate_text.split())[:700]

    @staticmethod
    def _chunk_text(candidate_text: str) -> list[str]:
        compacted = " ".join(candidate_text.split())
        if not compacted:
            return []
        chunks: list[str] = []
        for start in range(
            0, min(len(compacted), CANDIDATE_TEXT_CHARS), CANDIDATE_CHUNK_STRIDE
        ):
            chunk = compacted[start : start + CANDIDATE_CHUNK_CHARS].strip()
            if chunk:
                chunks.append(chunk)
            if start + CANDIDATE_CHUNK_CHARS >= len(compacted):
                break
        return chunks[:8]

    @staticmethod
    def _term_line(label: str, terms: list[str]) -> str:
        joined = ", ".join(term.strip() for term in terms if term.strip())
        return f"{label}: {joined}" if joined else ""

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("Embedding dimension mismatch for semantic similarity")
        if not left:
            return 0.0

        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return round(max(0.0, min(1.0, dot / (left_norm * right_norm))), 6)
