from pathlib import Path


def test_report_prompt_requests_structured_json_not_renderer_owned_markdown():
    content = Path("src/crews/analysis_crew.py").read_text(encoding="utf-8")

    assert "Return ONLY valid JSON" in content
    assert '"what_happened"' in content
    assert '"directly_observable"' in content
    assert "Do not include a Source Matrix or All Sources & Citations" in content
    assert (
        "The deterministic renderer will add layout, matrix, and citations" in content
    )
    assert "Logical Fallacies" in content
    assert "linguistic_manipulation" in content
    assert "fact_opinion_ambiguities" in content
    assert "Do not paste full article text" in content
    assert content.count("{prefetched_context}") == 1
