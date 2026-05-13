"""Application settings loaded from environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm_provider: str = "ollama"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b:free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    database_url: str = "sqlite+aiosqlite:///./data/tender_finder.db"
    upload_dir: str = "./data/uploads"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    search_provider: str = "duckduckgo"
    max_search_results: int = 8
    request_timeout_seconds: int = 15
    search_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
