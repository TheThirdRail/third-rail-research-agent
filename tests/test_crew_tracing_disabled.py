from pathlib import Path


def test_analysis_and_discovery_crews_disable_tracing():
    analysis = Path("src/crews/analysis_crew.py").read_text(encoding="utf-8")
    discovery = Path("src/crews/discovery_crew.py").read_text(encoding="utf-8")

    assert "tracing=False" in analysis
    assert "tracing=False" in discovery
