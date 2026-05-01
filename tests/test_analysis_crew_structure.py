from pathlib import Path
from types import SimpleNamespace

from src.crews.analysis_crew import _extract_final_report_payload


def test_analysis_crew_includes_rhetoric_and_narrative_tasks():
    content = Path("src/crews/analysis_crew.py").read_text(encoding="utf-8")

    assert "rhetoric_task = Task(" in content
    assert "narrative_task = Task(" in content
    assert "create_rhetorical_analyst_agent()" in content
    assert "create_narrative_analyzer_agent()" in content
    assert "context=[source_task, bias_task, fact_task, rhetoric_task]" in content
    normalized = " ".join(content.split())
    assert "return [" in normalized
    for task_name in (
        "source_task",
        "bias_task",
        "fact_task",
        "rhetoric_task",
        "narrative_task",
        "report_task",
    ):
        assert task_name in normalized


def test_analysis_crew_accepts_task_specific_semantic_contexts():
    content = Path("src/crews/analysis_crew.py").read_text(encoding="utf-8")

    assert "agent_contexts: dict[str, str] | None = None" in content
    assert '_agent_context_block(agent_contexts, "fact_extractor")' in content
    assert '_agent_context_block(agent_contexts, "rhetorical_analyst")' in content
    assert '_agent_context_block(agent_contexts, "narrative_analyzer")' in content
    assert '_agent_context_block(agent_contexts, "report_writer")' in content
    assert "Retrieved Semantic Context" in content


def test_extract_final_report_payload_prefers_last_task_json():
    result = SimpleNamespace(
        raw="# Wrapped Crew Transcript\n\nnot the final JSON",
        tasks_output=[
            SimpleNamespace(raw="intermediate"),
            SimpleNamespace(
                json_dict={
                    "executive_summary": "Structured final answer.",
                    "source_findings": [
                        {
                            "source_id": "S1",
                            "key_framing": "Frames the issue as regulatory overreach.",
                            "notable_claim": "Compliance costs are emphasized.",
                        }
                    ],
                }
            ),
        ],
    )

    payload = _extract_final_report_payload(result)

    assert payload["executive_summary"] == "Structured final answer."
    assert payload["source_findings"][0]["source_id"] == "S1"
