"""Tests for CORS origin validation."""

import os

os.environ.setdefault("APP_ENV", "test")

import pytest


def test_wildcard_cors_rejected(monkeypatch):
    """Wildcard CORS with credentials must raise ValueError."""
    monkeypatch.setenv("CORS_ORIGINS", "*")
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()

    from src.api.main import _cors_origins

    with pytest.raises(ValueError, match="Wildcard"):
        _cors_origins()

    # Cleanup
    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()


def test_explicit_origins_accepted(monkeypatch):
    """Explicit comma-separated origins are returned as-is."""
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://staging.example.com")
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()

    from src.api.main import _cors_origins

    origins = _cors_origins()
    assert origins == ["https://app.example.com", "https://staging.example.com"]

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()


def test_empty_cors_uses_defaults(monkeypatch):
    """Empty CORS_ORIGINS falls back to localhost defaults."""
    monkeypatch.setenv("CORS_ORIGINS", "")
    from src.core import config as _cfg

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()

    from src.api.main import _cors_origins

    origins = _cors_origins()
    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins

    _cfg.get_settings.cache_clear()
    _cfg.settings = _cfg.get_settings()
