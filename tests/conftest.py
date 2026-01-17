"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def sample_article_text() -> str:
    """Sample news article text for testing."""
    return """
    The Senate passed a new infrastructure bill today with bipartisan support.
    Senator John Smith (R) called it "a win for American workers," while 
    Senator Jane Doe (D) emphasized the environmental benefits. Critics 
    argue the bill doesn't go far enough on climate provisions.
    """


@pytest.fixture  
def sample_source_domains() -> list[str]:
    """Sample news source domains for testing."""
    return [
        "reuters.com",
        "cnn.com",
        "foxnews.com",
        "reason.com",
        "msnbc.com",
    ]
