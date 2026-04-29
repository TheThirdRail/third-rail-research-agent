"""Resolve political bias with dataset, AllSides, and LLM fallbacks."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.core.llm_provider_docker import get_llm_router
from src.services.allsides_client import AllSidesClient
from src.tools.bias_classifier import BIAS_LABELS, BiasClassifier, BiasResult

logger = logging.getLogger(__name__)


@dataclass
class BiasResolutionInput:
    """Input for bias resolution."""

    url: str
    domain: str
    article_text: str
    extra_texts: Iterable[str] = ()


class BiasResolutionService:
    """Resolve bias using dataset, AllSides, and LLM fallbacks."""

    def __init__(self) -> None:
        self._classifier = BiasClassifier()
        self._allsides = AllSidesClient()

    def resolve(
        self,
        input_data: BiasResolutionInput,
        extra_texts_provider: Callable[[], Iterable[str]] | None = None,
    ) -> BiasResult:
        """Resolve bias for a source with fallbacks."""
        # 1) Local dataset lookup
        result = self._classifier.local_db.lookup(input_data.domain)
        if result:
            return result

        # 2) AllSides lookup
        allsides_result = self._allsides.lookup_domain(input_data.domain)
        if allsides_result:
            return allsides_result

        # 3) LLM inference with contextual cues
        try:
            extra_texts = list(input_data.extra_texts)
            if extra_texts_provider:
                extra_texts = list(extra_texts_provider())
            input_with_extras = BiasResolutionInput(
                url=input_data.url,
                domain=input_data.domain,
                article_text=input_data.article_text,
                extra_texts=extra_texts,
            )
            return self._llm_infer_bias(input_with_extras)
        except Exception as exc:
            logger.warning("LLM bias inference failed: %s", exc)
            return self._simple_heuristic(input_data.domain, input_data.article_text)

    def _llm_infer_bias(self, input_data: BiasResolutionInput) -> BiasResult:
        router = get_llm_router(agent_name="bias_classifier")
        excerpts = [input_data.article_text]
        for text in input_data.extra_texts:
            if text:
                excerpts.append(text)

        combined = "\n\n---\n\n".join(excerpts)[:4000]
        prompt = f"""Analyze the political bias of this news source based on reporting style,
framing, and language. If you are uncertain, make a best-effort estimate.

Domain: {input_data.domain}
Article excerpts:
{combined}

Classify on a 9-point scale:
-4 = Far Left, -3 = Left, -2 = Lean Left, -1 = Slight Left
 0 = Center
 +1 = Slight Right, +2 = Lean Right, +3 = Right, +4 = Far Right

Respond with ONLY a JSON object (no markdown, no explanation):
{{"bias": <number -4 to 4>, "confidence": <0.0-1.0>}}"""

        response = router.complete(
            [{"role": "user", "content": prompt}], max_tokens=120
        )
        bias, confidence = self._parse_json_bias(response)
        bias = max(-4, min(4, bias))
        return BiasResult(
            domain=input_data.domain,
            bias=bias,
            bias_label=BIAS_LABELS.get(bias, "Unknown"),
            confidence=confidence,
            method="llm",
            factual_rating=None,
            category=None,
        )

    def _parse_json_bias(self, response: str) -> tuple[int, float]:
        import json

        match = re.search(r"\{[^}]+\}", response)
        if not match:
            raise ValueError("No JSON object found in LLM response")
        data = json.loads(match.group())
        bias = int(data.get("bias", 0))
        confidence = float(data.get("confidence", 0.5))
        return bias, max(0.0, min(1.0, confidence))

    def _simple_heuristic(self, domain: str, text: str) -> BiasResult:
        text_lower = text.lower()
        left_keywords = [
            "progressive",
            "social justice",
            "inequality",
            "systemic",
            "marginalized",
        ]
        right_keywords = [
            "freedom",
            "liberty",
            "constitution",
            "traditional",
            "patriot",
        ]

        left_count = sum(1 for kw in left_keywords if kw in text_lower)
        right_count = sum(1 for kw in right_keywords if kw in text_lower)

        if left_count > right_count + 2:
            bias = -2
        elif right_count > left_count + 2:
            bias = 2
        else:
            bias = 0

        return BiasResult(
            domain=domain,
            bias=bias,
            bias_label=BIAS_LABELS.get(bias, "Unknown"),
            confidence=0.2,
            method="heuristic",
            factual_rating=None,
            category=None,
        )
