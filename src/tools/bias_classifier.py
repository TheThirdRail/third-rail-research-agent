"""Political Bias Classification Tool for CrewAI."""

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import yaml
from crewai.tools.base_tool import BaseTool

from src.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class BiasResult:
    """Result of bias classification."""

    domain: str
    bias: int  # -4 to +4
    bias_label: str
    confidence: float  # 0.0 to 1.0
    method: str  # dataset, llm, manual
    factual_rating: str | None
    category: str | None  # libertarian, independent, etc.


# Bias labels for 9-point scale
BIAS_LABELS = {
    -4: "Far Left",
    -3: "Left",
    -2: "Lean Left",
    -1: "Slight Left",
    0: "Center",
    1: "Slight Right",
    2: "Lean Right",
    3: "Right",
    4: "Far Right",
}


class LocalBiasDatabase:
    """Local database of known source bias ratings."""

    def __init__(self, config_path: str | None = None):
        """Initialize with configuration file."""
        self.config_path = config_path or str(settings.config_dir / "bias_sources.yaml")
        self.sources = self._load_sources()

    def _load_sources(self) -> dict[str, dict]:
        """Load sources from configuration."""
        try:
            with open(self.config_path) as f:
                config = yaml.safe_load(f)
            return config.get("sources", {})
        except Exception as e:
            logger.error(f"Failed to load bias sources: {e}")
            return {}

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain for lookup."""
        domain = domain.lower().strip()
        domain = domain.replace("www.", "")
        return domain

    def lookup(self, domain: str) -> BiasResult | None:
        """Look up bias for a domain."""
        normalized = self._normalize_domain(domain)

        if normalized in self.sources:
            source = self.sources[normalized]
            return BiasResult(
                domain=normalized,
                bias=source.get("bias", 0),
                bias_label=BIAS_LABELS.get(source.get("bias", 0), "Unknown"),
                confidence=1.0,  # High confidence for known sources
                method="dataset",
                factual_rating=source.get("factual"),
                category=source.get("category"),
            )

        return None


class BiasClassifier:
    """Classifies political bias of news sources."""

    def __init__(self):
        """Initialize classifier."""
        self.local_db = LocalBiasDatabase()

    def _extract_domain(self, url_or_domain: str) -> str:
        """Extract domain from URL or clean domain string."""
        if url_or_domain.startswith("http"):
            try:
                parsed = urlparse(url_or_domain)
                return parsed.netloc.replace("www.", "")
            except Exception:
                pass
        return url_or_domain.replace("www.", "").lower().strip()

    def classify(self, url_or_domain: str, article_text: str = "") -> BiasResult:
        """Classify bias of a source.

        First tries local dataset lookup.
        Falls back to heuristic analysis if article_text provided.
        Returns unknown bias if no classification possible.
        """
        domain = self._extract_domain(url_or_domain)

        # Try local database first
        result = self.local_db.lookup(domain)
        if result:
            return result

        # For unknown sources, use heuristic based on text if available
        if article_text:
            return self._heuristic_classify(domain, article_text)

        # Unknown source with no text
        return BiasResult(
            domain=domain,
            bias=0,
            bias_label="Unknown",
            confidence=0.0,
            method="unknown",
            factual_rating=None,
            category=None,
        )

    def _heuristic_classify(self, domain: str, text: str) -> BiasResult:
        """Classify bias using LLM analysis.

        Uses the LLMRouter for intelligent classification of unknown sources.
        Falls back to simple heuristic if LLM fails.
        """
        # Try LLM classification first
        try:
            return self._llm_classify(domain, text)
        except Exception as e:
            logger.warning(f"LLM classification failed, using heuristic: {e}")
            return self._simple_heuristic(domain, text)

    def _llm_classify(self, domain: str, text: str) -> BiasResult:
        """Use LLM for bias classification."""
        from src.core.llm_provider import get_llm_router

        router = get_llm_router()

        prompt = f"""Analyze the political bias of this news source and article.

Domain: {domain}
Article excerpt (first 1500 chars):
{text[:1500]}

Classify the political bias on a 9-point scale:
-4 = Far Left, -3 = Left, -2 = Lean Left, -1 = Slight Left
0 = Center
+1 = Slight Right, +2 = Lean Right, +3 = Right, +4 = Far Right

Also identify if this is a libertarian or independent source.

Respond with ONLY a JSON object (no markdown, no explanation):
{{"bias": <number -4 to 4>, "category": "<libertarian|independent|mainstream|null>", "confidence": <0.0-1.0>}}"""

        response = router.complete(
            [{"role": "user", "content": prompt}], max_tokens=100
        )

        # Parse JSON from response
        import json
        import re

        # Extract JSON from response
        json_match = re.search(r"\{[^}]+\}", response)
        if json_match:
            data = json.loads(json_match.group())
            bias = max(-4, min(4, int(data.get("bias", 0))))
            return BiasResult(
                domain=domain,
                bias=bias,
                bias_label=BIAS_LABELS.get(bias, "Unknown"),
                confidence=float(data.get("confidence", 0.7)),
                method="llm",
                factual_rating=None,
                category=data.get("category"),
            )

        raise ValueError("Could not parse LLM response")

    def _simple_heuristic(self, domain: str, text: str) -> BiasResult:
        """Simple keyword-based fallback when LLM unavailable."""
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
        libertarian_keywords = [
            "libertarian",
            "non-intervention",
            "individual rights",
            "civil liberties",
        ]

        left_count = sum(1 for kw in left_keywords if kw in text_lower)
        right_count = sum(1 for kw in right_keywords if kw in text_lower)
        lib_count = sum(1 for kw in libertarian_keywords if kw in text_lower)

        if lib_count > left_count and lib_count > right_count:
            bias, category = 0, "libertarian"
        elif left_count > right_count + 3:
            bias, category = -2, None
        elif right_count > left_count + 3:
            bias, category = 2, None
        else:
            bias, category = 0, None

        return BiasResult(
            domain=domain,
            bias=bias,
            bias_label=BIAS_LABELS.get(bias, "Unknown"),
            confidence=0.3,
            method="heuristic",
            factual_rating=None,
            category=category,
        )


class BiasClassifierTool(BaseTool):
    """CrewAI tool for political bias classification."""

    name: str = "Bias Classifier"
    description: str = """Classifies the political bias of a news source on a 9-point scale
    from -4 (Far Left) to +4 (Far Right). Provide a domain name or URL.
    Optionally provide article text for better classification of unknown sources.
    Returns bias rating, confidence level, and factual rating if known."""

    def _run(
        self,
        source: str,
        article_text: str = "",
    ) -> str:
        """Execute bias classification.

        Args:
            source: Domain name or URL of the source
            article_text: Optional article text for contextual analysis

        Returns:
            Formatted bias classification result
        """
        classifier = BiasClassifier()
        result = classifier.classify(source, article_text)

        # Format output
        output = f"""=== BIAS CLASSIFICATION ===
Domain: {result.domain}
Bias Score: {result.bias} ({result.bias_label})
Confidence: {result.confidence:.0%}
Method: {result.method}
"""

        if result.factual_rating:
            output += f"Factual Rating: {result.factual_rating}\n"

        if result.category:
            output += f"Category: {result.category}\n"

        # Add interpretation
        if result.bias < -2:
            output += "\nInterpretation: Strong left-leaning perspective. May emphasize progressive viewpoints."
        elif result.bias > 2:
            output += "\nInterpretation: Strong right-leaning perspective. May emphasize conservative viewpoints."
        elif result.category == "libertarian":
            output += "\nInterpretation: Libertarian source. May not fit traditional left-right spectrum."
        elif abs(result.bias) <= 1:
            output += "\nInterpretation: Relatively balanced or centrist coverage."

        return output


class MultiBiasClassifierTool(BaseTool):
    """CrewAI tool for classifying multiple sources at once."""

    name: str = "Multi-Source Bias Classifier"
    description: str = """Classifies political bias for multiple news sources at once.
    Provide sources as comma-separated domains or URLs.
    Returns a comparison table of bias ratings."""

    def _run(self, sources: str) -> str:
        """Classify multiple sources.

        Args:
            sources: Comma or newline-separated list of domains/URLs

        Returns:
            Formatted comparison table
        """
        # Parse sources
        source_list = [
            s.strip() for s in sources.replace(",", "\n").split("\n") if s.strip()
        ]

        if not source_list:
            return "No sources provided."

        classifier = BiasClassifier()
        results = []

        for source in source_list[:20]:  # Max 20 sources
            result = classifier.classify(source)
            results.append(result)

        # Create comparison table
        output_lines = ["=== BIAS COMPARISON ===\n"]
        output_lines.append(f"{'Source':<30} {'Bias':>6} {'Label':<15} {'Conf':>6}\n")
        output_lines.append("-" * 65 + "\n")

        for r in sorted(results, key=lambda x: x.bias):
            output_lines.append(
                f"{r.domain[:28]:<30} {r.bias:>+5}  {r.bias_label:<15} {r.confidence:>5.0%}\n"
            )

        # Summary statistics
        known = [r for r in results if r.method == "dataset"]
        output_lines.append(f"\nSources found in database: {len(known)}/{len(results)}")

        left = [r for r in results if r.bias < 0]
        center = [r for r in results if r.bias == 0]
        right = [r for r in results if r.bias > 0]

        output_lines.append(
            f"Distribution: Left={len(left)}, Center={len(center)}, Right={len(right)}"
        )

        return "".join(output_lines)
