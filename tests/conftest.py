"""Pytest configuration and fixtures."""

import pytest
from sqlalchemy import create_engine

from src.database.models import Base


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


@pytest.fixture
def temp_database_url(tmp_path, monkeypatch) -> str:
    """Use an isolated SQLite database for tests that read DATABASE_URL."""
    db_path = tmp_path / "test_research_agent.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    return database_url


@pytest.fixture
def temp_database_engine(temp_database_url):
    """Create an isolated SQLAlchemy engine with the current metadata."""
    engine = create_engine(temp_database_url)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()
