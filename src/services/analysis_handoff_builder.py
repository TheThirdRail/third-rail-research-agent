"""Handoff and durable finding helpers for analysis runs."""

import json
import re
from typing import Any

from src.schemas.analysis_report_sections import AnalysisReportSections
from src.schemas.visual_evidence import VisualEvidenceBundle


class AnalysisHandoffBuilder:
    """Build handoff summaries, payloads, and persisted agent finding specs."""

    def retrieval_summary(self, coverage: dict[str, Any]) -> str:
        missing = coverage.get("missing_buckets") or []
        missing_text = ", ".join(missing) if missing else "none"
        return (
            f"Retrieved {coverage.get('retained_count', 0)} sources after probing "
            f"{coverage.get('probed_count', 0)} candidates; missing buckets: "
            f"{missing_text}."
        )

    def pre_crew_summary(
        self,
        coverage: dict[str, Any],
        semantic_agent_contexts: dict[str, str],
        visual_bundle: VisualEvidenceBundle,
    ) -> str:
        return (
            f"Prepared crew context for {coverage.get('retained_count', 0)} sources, "
            f"{len(semantic_agent_contexts)} semantic context lanes, and "
            f"{len(visual_bundle.records)} visual evidence records."
        )

    def agent_finding_specs(
        self,
        sections: AnalysisReportSections,
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = [
            {
                "agent_name": "fact_extractor",
                "document_type": "fact_claims",
                "finding_type": "fact_claims",
                "section_fields": [
                    "what_happened",
                    "directly_observable",
                    "agreed_facts",
                    "what_is_disputed",
                ],
                "text": self.join_section_parts(
                    [
                        ("What happened", sections.what_happened),
                        ("Directly observable", sections.directly_observable),
                        ("Agreed facts", sections.agreed_facts),
                        ("What is disputed", sections.what_is_disputed),
                    ]
                ),
            },
            {
                "agent_name": "rhetorical_analyst",
                "document_type": "rhetoric_findings",
                "finding_type": "rhetoric_findings",
                "section_fields": [
                    "framing_omissions",
                    "logical_fallacies",
                    "linguistic_manipulation",
                    "fact_opinion_ambiguities",
                ],
                "text": self.join_section_parts(
                    [
                        ("Framing omissions", sections.framing_omissions),
                        ("Logical fallacies", sections.logical_fallacies),
                        (
                            "Linguistic manipulation",
                            sections.linguistic_manipulation,
                        ),
                        (
                            "Fact-opinion ambiguities",
                            sections.fact_opinion_ambiguities,
                        ),
                    ]
                ),
            },
            {
                "agent_name": "narrative_analyzer",
                "document_type": "narrative_findings",
                "finding_type": "narrative_findings",
                "section_fields": [
                    "mainstream_narrative",
                    "alternative_takes",
                    "creator_angles",
                    "recommended_approach",
                    "video_outline",
                ],
                "text": self.join_section_parts(
                    [
                        ("Mainstream narrative", sections.mainstream_narrative),
                        ("Alternative takes", sections.alternative_takes),
                        ("Creator angles", sections.creator_angles),
                        ("Recommended approach", sections.recommended_approach),
                        ("Video outline", sections.video_outline),
                    ]
                ),
            },
            {
                "agent_name": "narrative_analyzer",
                "document_type": "coverage_asymmetry",
                "finding_type": "coverage_asymmetry",
                "section_fields": ["coverage_snapshot", "evidence_limitations"],
                "text": self.join_section_parts(
                    [
                        ("Coverage snapshot", sections.coverage_snapshot),
                        ("Evidence limitations", sections.evidence_limitations),
                        (
                            "Coverage diagnostics",
                            json.dumps(coverage, sort_keys=True),
                        ),
                    ]
                ),
            },
        ]
        durable_specs: list[dict[str, Any]] = []
        for spec in specs:
            if not spec["text"].strip():
                continue
            source_refs = self.source_refs_from_text(spec["text"])
            durable_specs.append(
                {
                    **spec,
                    "source_refs": source_refs,
                    "metadata": {
                        "document_type": spec["document_type"],
                        "section_fields": spec["section_fields"],
                    },
                }
            )
        return durable_specs

    def agent_handoffs_from_findings(
        self,
        finding_specs: list[dict[str, Any]],
        coverage: dict[str, Any],
    ) -> list[dict[str, Any]]:
        stage_by_agent = {
            "fact_extractor": "fact_handoff",
            "rhetorical_analyst": "rhetoric_handoff",
            "narrative_analyzer": "narrative_handoff",
        }
        handoffs = []
        for spec in finding_specs:
            agent_name = spec["agent_name"]
            stage = stage_by_agent.get(agent_name, "report_handoff")
            handoffs.append(
                {
                    "stage": stage,
                    "from_agent": agent_name,
                    "to_agent": "report_writer",
                    "summary": self.compact_summary(spec["text"]),
                    "payload": {
                        "finding_type": spec["finding_type"],
                        "document_type": spec["document_type"],
                        "section_fields": spec["section_fields"],
                        "source_refs": spec["source_refs"],
                        "coverage_satisfied": bool(coverage.get("coverage_satisfied")),
                    },
                }
            )
        return handoffs

    def coverage_snapshot(self, coverage: dict[str, Any]) -> str:
        exact_counts = coverage.get("exact_bias_counts") or {}
        exact_parts = [
            f"{bias:+d}: {count}"
            for bias, count in sorted(
                exact_counts.items(), key=lambda item: int(item[0])
            )
        ]
        missing = coverage.get("missing_buckets") or []
        missing_text = ", ".join(missing) if missing else "none"
        exact_text = ", ".join(exact_parts) if exact_parts else "unavailable"
        return (
            f"Retained {coverage.get('retained_count', 0)} sources after probing "
            f"{coverage.get('probed_count', 0)} candidates. "
            f"Grouped counts: left={coverage.get('left_count', 0)}, "
            f"center={coverage.get('center_count', 0)}, "
            f"right={coverage.get('right_count', 0)}. "
            f"Exact-bias counts: {exact_text}. Missing required buckets: {missing_text}."
        )

    @staticmethod
    def compact_summary(text: str, max_chars: int = 280) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars].rstrip() + "..."

    @staticmethod
    def join_section_parts(parts: list[tuple[str, object]]) -> str:
        lines: list[str] = []
        for label, value in parts:
            if isinstance(value, list):
                text = "\n".join(f"- {item}" for item in value if str(item).strip())
            else:
                text = str(value or "").strip()
            if text:
                lines.append(f"{label}:\n{text}")
        return "\n\n".join(lines)

    @staticmethod
    def source_refs_from_text(text: str) -> list[str]:
        return sorted(
            set(re.findall(r"\bS\d+\b", text or "")),
            key=lambda ref: int(ref[1:]),
        )
