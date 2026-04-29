"""Application configuration using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    app_env: Literal["development", "production", "test"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    @field_validator("debug", mode="before")
    @classmethod
    def _normalize_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    # LLM Provider Selection
    llm_provider: str = Field(
        default="openrouter",
        description=(
            "Primary LLM provider: openrouter|gemini|anthropic|groq|openai|grok|"
            "cerebras|sambanova|mistral|lmstudio|ollama"
        ),
    )

    # OpenRouter
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Google Gemini
    google_api_key: str = Field(
        default="", description="Google Gemini API key (legacy)"
    )
    gemini_api_key: str = Field(default="", description="Google Gemini API key")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")

    # Groq
    groq_api_key: str = Field(default="", description="Groq API key")

    # OpenAI / Compatible
    openai_api_key: str = Field(default="", description="OpenAI API key")
    openai_base_url: str = Field(default="", description="OpenAI-compatible base URL")

    # Optional Codex OAuth testing (local-only)
    codex_oauth_testing_enabled: bool = False
    codex_oauth_mode: Literal[
        "disabled", "openai_compatible_bridge", "codex_cli"
    ] = "disabled"
    codex_cli_command: str = "codex"
    codex_require_localhost: bool = True
    codex_allow_public_api: bool = False
    codex_max_prompt_chars: int = 30000
    codex_timeout_seconds: int = 300

    # LM Studio (local OpenAI-compatible)
    lmstudio_api_key: str = Field(
        default="",
        description="LM Studio API key (optional)",
        validation_alias=AliasChoices("LMSTUDIO_API_KEY", "LM_STUDIO_API_KEY"),
    )
    lmstudio_base_url: str = Field(
        default="http://localhost:1234",
        description="LM Studio OpenAI-compatible base URL",
        validation_alias=AliasChoices(
            "LMSTUDIO_BASE_URL", "LM_STUDIO_BASE_URL", "LM_STUDIO_API_BASE"
        ),
    )
    lmstudio_fallback_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "LMSTUDIO_FALLBACK_ENABLED", "LM_STUDIO_FALLBACK_ENABLED"
        ),
    )
    lmstudio_fallback_model: str = Field(
        default="qwen2.5-7b-instruct",
        description="Fallback local LM Studio model ID",
        validation_alias=AliasChoices(
            "LMSTUDIO_FALLBACK_MODEL", "LM_STUDIO_FALLBACK_MODEL"
        ),
    )

    # Grok (xAI)
    xai_api_key: str = Field(default="", description="xAI Grok API key")

    # Cerebras
    cerebras_api_key: str = Field(default="", description="Cerebras API key")

    # SambaNova
    sambanova_api_key: str = Field(default="", description="SambaNova API key")

    # Mistral AI
    mistral_api_key: str = Field(default="", description="Mistral AI API key")

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"

    # SearxNG (self-hosted search)
    searxng_base_url: str = Field(
        default="", description="SearxNG base URL (e.g., http://localhost:8080)"
    )
    searxng_api_key: str = Field(
        default="", description="Optional SearxNG API key for protected instances"
    )

    # Model Selection (dynamic - set via API or config file)
    selected_model: str = Field(
        default="", description="Selected model ID (provider/model)"
    )
    analysis_model: str = Field(default="", description="Model for analysis tasks")

    # Extraction and discovery fallbacks
    enable_selenium_fallback: bool = True
    max_selenium_attempts: int = 1
    selenium_headless: bool = True
    selenium_timeout_seconds: int = 25
    selenium_user_agents: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36||"
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    )
    rss_seed_fallback_enabled: bool = True
    discovery_enrichment_enabled: bool = True

    # Source gathering policy
    candidate_probe_limit: int = Field(
        default=15, description="Max candidate URLs to search/extract before stopping"
    )
    retained_source_min: int = Field(
        default=3, description="Minimum final retained sources"
    )
    retained_source_max: int = Field(
        default=5, description="Maximum final retained sources"
    )
    search_time_window_days: int = Field(
        default=7, description="Default ±days for event-based search window"
    )
    strict_bucket_enforcement: bool = Field(
        default=True, description="Fail/warn if required bias buckets are missing"
    )
    required_bucket_groups: str = Field(
        default="left_side,right_side",
        description="Comma-separated required source bucket groups",
    )
    exact_center_preferred: bool = Field(
        default=True,
        description="Prefer an exact-center source when available, but do not require it",
    )
    max_per_exact_bias: int = Field(
        default=1,
        description="Maximum retained sources with the same exact bias score",
    )
    max_per_bucket_group: int = Field(
        default=2,
        description="Maximum retained sources from the same bias bucket group",
    )
    allow_same_bias_backfill: bool = Field(
        default=False,
        description="Allow same-bias padding when required buckets are missing",
    )
    analysis_rss_first_enabled: bool = Field(
        default=True,
        description="Search canonical RSS feeds before site/open-web search",
    )
    analysis_rss_timeout_seconds: int = Field(
        default=6,
        description="Per-feed timeout for analysis-time RSS retrieval",
    )
    analysis_rss_max_feeds_per_bucket: int = Field(
        default=3,
        description="Maximum RSS feeds to fetch for a single planned bucket",
    )

    # Database
    database_url: str = "sqlite:///data/research_agent.db"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Paths
    @property
    def project_root(self) -> Path:
        """Get project root directory."""
        return Path(__file__).parent.parent.parent

    @property
    def config_dir(self) -> Path:
        """Get config directory."""
        return self.project_root / "config"

    @property
    def data_dir(self) -> Path:
        """Get data directory."""
        return self.project_root / "data"

    @property
    def channel_profile_path(self) -> Path:
        """Get channel profile config path."""
        return self.config_dir / "channel_profile.yaml"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience export
settings = get_settings()

# Back-compat: allow GEMINI_API_KEY to satisfy GOOGLE_API_KEY lookups.
if settings.gemini_api_key and not settings.google_api_key:
    settings.google_api_key = settings.gemini_api_key
    os.environ.setdefault("GOOGLE_API_KEY", settings.gemini_api_key)
