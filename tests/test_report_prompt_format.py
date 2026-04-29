from pathlib import Path


def test_report_prompt_includes_table_and_citations():
    content = Path("src/crews/analysis_crew.py").read_text(encoding="utf-8")

    assert "Source Matrix (all sources with bias ratings) as a Markdown table" in content
    assert (
        "| Source | Domain | URL | Bias (score+label) | Confidence | Key Framing / Claim |"
        in content
    )
    assert "GFM footnotes" in content
    assert "[^1]: Source Name — https://example.com/article" in content
    assert "S1 [Headline text](https://example.com/article)" in content
    assert "Framing & Context Omissions" in content
    assert "Logical Fallacies" in content
    assert "Linguistic Manipulation & Dog Whistles" in content
    assert "Fact vs Opinion Ambiguities" in content
    assert "Additional Rhetorical Signals" in content
    assert "moderate verbosity" in content
    assert "Do not paste full article text" in content
    assert content.count("{prefetched_context}") == 1
