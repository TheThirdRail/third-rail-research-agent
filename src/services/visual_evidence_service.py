"""Visual evidence extraction through the existing LLM provider abstraction."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.core.llm_provider_docker import get_llm_router
from src.schemas.visual_evidence import (
    MediaPointer,
    VisualEvidenceBundle,
    VisualEvidenceRecord,
)

logger = logging.getLogger(__name__)


class VisualEvidenceService:
    """Turn article media pointers into observable-evidence records."""

    def analyze(self, pointers: list[MediaPointer]) -> VisualEvidenceBundle:
        if not pointers:
            return VisualEvidenceBundle()

        records: list[VisualEvidenceRecord] = []
        limitations: list[str] = []
        for pointer in pointers[:5]:
            if pointer.media_type == "image" and pointer.media_url.startswith("http"):
                try:
                    records.append(self._analyze_with_model(pointer))
                    continue
                except Exception as exc:
                    logger.warning("Visual evidence analysis failed: %s", exc)
                    limitations.append(
                        f"Visual model analysis failed for {pointer.media_url}: {exc}"
                    )
            metadata_record = self._record_from_metadata(pointer)
            if metadata_record:
                records.append(metadata_record)

        return VisualEvidenceBundle(records=records, limitations=limitations)

    def _analyze_with_model(self, pointer: MediaPointer) -> VisualEvidenceRecord:
        router = get_llm_router(agent_name="visual_evidence")
        prompt = (
            "Describe only what is directly observable in this media. "
            "Return JSON with keys observable_text, visible_symbols_or_numbers, "
            "observable_objects, platform, confidence. Do not infer intent, motive, "
            "political meaning, or legal characterization."
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Source URL: {pointer.source_url}\n"
                            f"Alt text: {pointer.alt_text}\n"
                            f"Caption: {pointer.caption}"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": pointer.media_url},
                    },
                ],
            },
        ]
        raw = router.complete(messages, temperature=0.1, max_tokens=900)
        data = self._parse_json(raw)
        return VisualEvidenceRecord(
            source_url=pointer.source_url,
            media_url=pointer.media_url,
            media_type=pointer.media_type,
            platform=str(data.get("platform") or pointer.platform or ""),
            observable_text=str(data.get("observable_text") or ""),
            visible_symbols_or_numbers=self._as_string_list(
                data.get("visible_symbols_or_numbers")
            ),
            observable_objects=self._as_string_list(data.get("observable_objects")),
            reported_context=self._metadata_context(pointer),
            interpretation="",
            legal_characterization="",
            confidence=self._confidence(data.get("confidence")),
        )

    def _record_from_metadata(
        self,
        pointer: MediaPointer,
    ) -> VisualEvidenceRecord | None:
        text = self._metadata_context(pointer)
        if not text:
            return None
        symbols = re.findall(r"\b[A-Z0-9]{2,8}\b", text)
        return VisualEvidenceRecord(
            source_url=pointer.source_url,
            media_url=pointer.media_url,
            media_type=pointer.media_type,
            platform=pointer.platform,
            observable_text=text,
            visible_symbols_or_numbers=symbols,
            observable_objects=[],
            reported_context=text,
            interpretation="",
            legal_characterization="",
            confidence=0.4,
        )

    @staticmethod
    def _metadata_context(pointer: MediaPointer) -> str:
        parts = [pointer.alt_text.strip(), pointer.caption.strip()]
        return " ".join(part for part in parts if part).strip()

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        elif not text.startswith("{"):
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if not match:
                raise ValueError("visual model did not return JSON")
            text = match.group(1)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("visual model returned non-object JSON")
        return parsed

    @staticmethod
    def _as_string_list(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    @staticmethod
    def _confidence(value: object) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except Exception:
            return 0.5
