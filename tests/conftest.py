"""Pytest configuration and fixtures."""

import logging

import pytest
from sqlalchemy import create_engine

from src.core import config as core_config
from src.core import embedding_provider as embedding_provider_module
from src.database.models import Base
from src.services import analysis_service as analysis_service_module
from src.services import semantic_memory_service as semantic_memory_service_module
from src.services import source_aggregator_service as source_aggregator_service_module
from src.services import vector_store_service as vector_store_service_module


@pytest.fixture(autouse=True)
def isolate_live_semantic_runtime_settings(monkeypatch) -> None:
    """Keep default tests from inheriting live embedding/vector-store settings."""
    monkeypatch.setattr(embedding_provider_module, "settings", core_config.settings)
    monkeypatch.setattr(
        semantic_memory_service_module, "settings", core_config.settings
    )
    monkeypatch.setattr(vector_store_service_module, "settings", core_config.settings)
    monkeypatch.setattr(
        source_aggregator_service_module, "settings", core_config.settings
    )
    monkeypatch.setattr(analysis_service_module, "settings", core_config.settings)

    settings_refs = (
        core_config.settings,
        embedding_provider_module.settings,
        semantic_memory_service_module.settings,
        vector_store_service_module.settings,
        source_aggregator_service_module.settings,
        analysis_service_module.settings,
    )
    for settings in settings_refs:
        monkeypatch.setattr(settings, "semantic_memory_enabled", False)
        monkeypatch.setattr(settings, "semantic_candidate_scoring_enabled", False)
        monkeypatch.setattr(settings, "embedding_provider", "fake")
        monkeypatch.setattr(settings, "embedding_model", "fake-hash-v1")
        monkeypatch.setattr(settings, "semantic_vector_store", "none")


@pytest.fixture(autouse=True)
def isolate_logging_capture_state(monkeypatch) -> None:
    """Reset global logger muting so caplog assertions stay order independent."""
    logging.disable(logging.NOTSET)
    for logger_name in (
        "src.api.routes.channel",
        "src.tools.channel_profile_loader",
    ):
        logger = logging.getLogger(logger_name)
        monkeypatch.setattr(logger, "disabled", False)
        monkeypatch.setattr(logger, "propagate", True)


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
