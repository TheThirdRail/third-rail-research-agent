from pathlib import Path


def test_analysis_crew_includes_rhetoric_and_narrative_tasks():
    content = Path("src/crews/analysis_crew.py").read_text(encoding="utf-8")

    assert "rhetoric_task = Task(" in content
    assert "narrative_task = Task(" in content
    assert "create_rhetorical_analyst_agent()" in content
    assert "create_narrative_analyzer_agent()" in content
    assert "context=[source_task, bias_task, fact_task, rhetoric_task]" in content
    assert (
        "return [source_task, bias_task, fact_task, rhetoric_task, narrative_task, report_task]"
        in content
    )
