"""Backend settings from environment variables (see docker-compose.yml / .env.example)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTI_", env_file=".env", extra="ignore")

    data_dir: str = "./data"
    database_url: str = ""  # default: sqlite in data_dir
    secret_key: str = "change-me-in-production"
    admin_email: str = "admin@senti.local"
    admin_password: str = "senti-admin"
    org_name: str = "Acme Corp"
    demo_enroll_code: str = "SENTI-DEMO"
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    # corporate model (OpenAI-compatible chat completions endpoint, e.g. Ollama)
    corp_model_url: str = "http://localhost:11434/v1"
    corp_model: str = "qwen2.5:3b"
    corp_model_api_key: str = ""
    corp_timeout_s: float = 25.0
    token_ttl_hours: int = 12

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir}/senti.db"


settings = Settings()
