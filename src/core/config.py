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

    # OpenRouter (Primary LLM)
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    
    # Default models (free tier on OpenRouter)
    default_model: str = "meta-llama/llama-4-maverick:free"
    analysis_model: str = "deepseek/deepseek-chat-v3-0324:free"
    
    # Ollama (Optional fallback)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    use_ollama_fallback: bool = False

    # Database
    database_url: str = "sqlite:///data/performance.db"

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
