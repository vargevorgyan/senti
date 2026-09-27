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
    demo_enroll_code: str = ""  # set SENTI_DEMO_ENROLL_CODE for demos only (20 uses, 7 days)
    # Shared (multi-use, not tied to a person) enrollment codes: off. Admins invite people instead (personal, one-time keys).
    allow_shared_codes: bool = False
    invite_ttl_hours: int = 48
    # Per-device limits on the device API (requests per minute), so a leaked or rogue device can't burn the corporate model
    judge_rpm: int = 60
    approvals_rpm: int = 20
    cors_origins: str = "http://localhost:8080,http://localhost:5173"
    # corporate model (OpenAI-compatible chat completions endpoint, e.g. Ollama)
    corp_model_url: str = "http://localhost:11434/v1"
    corp_model: str = "qwen2.5:3b"
    corp_model_api_key: str = ""
    corp_timeout_s: float = 25.0
    token_ttl_hours: int = 12
    tls_cert: str = ""       # path to the TLS certificate served by the admin container
    https_port: int = 8443

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir}/senti.db"


settings = Settings()
