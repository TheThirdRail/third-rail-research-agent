"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
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

    # LLM Provider Selection
    llm_provider: str = Field(
        default="openrouter",
        description="Primary LLM provider: openrouter|gemini|anthropic|groq|openai|grok|cerebras|sambanova|ollama",
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

    # Model Selection (dynamic - set via API or config file)
    selected_model: str = Field(
        default="", description="Selected model ID (provider/model)"
    )
    analysis_model: str = Field(default="", description="Model for analysis tasks")

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
