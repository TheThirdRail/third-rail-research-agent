import pytest

from src.core.exceptions import SourceExtractionError
from src.services.report_validator import validate_report_sources


def test_report_validator_accepts_allowed_sources():
    report = """# Research Report

## 3. Source Matrix
| Source (Headline Link) | Domain | Bias (score+label) | Confidence | Key Framing / Claim |
| --- | --- | --- | --- | --- |
| [Test Story](https://example.com/news/story) | example.com | 0 (Center) | 0.8 | Neutral |
"""
    validate_report_sources(report, ["https://example.com/news/story"])


def test_report_validator_rejects_unknown_sources():
    report = """## Source Matrix
| Source (Headline Link) | Domain | Bias (score+label) | Confidence | Key Framing / Claim |
| --- | --- | --- | --- | --- |
| [Other Story](https://other.com/news) | other.com | 0 (Center) | 0.5 | Neutral |
"""
    with pytest.raises(SourceExtractionError):
        validate_report_sources(report, ["https://example.com/news/story"])


def test_report_validator_requires_source_matrix():
    report = "# Research Report\n\nNo matrix here."
    with pytest.raises(SourceExtractionError):
        validate_report_sources(report, ["https://example.com/news/story"])


def test_report_validator_rejects_footnote_urls_outside_source_matrix():
    report = """## Source Matrix
| Source (Headline Link) | Domain | Bias (score+label) | Confidence | Key Framing / Claim |
| --- | --- | --- | --- | --- |
| [Test Story](https://example.com/news/story) | example.com | 0 (Center) | 0.8 | Neutral |

## All Sources & Citations
[^1]: Test Story — https://example.com/news/story
[^2]: Unknown Source — https://unknown.example/other-story
"""
    with pytest.raises(SourceExtractionError):
        validate_report_sources(report, ["https://example.com/news/story"])
