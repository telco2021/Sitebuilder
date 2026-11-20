"""Runtime configuration. Secrets come from the environment, never from source."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LIQUID_", env_file=".env", extra="ignore")

    env: str = "development"
    secret_key: str = ""
    secret_file: str = "./data/secret.key"
    database_url: str = "sqlite:///./data/liquid.db"
    upload_dir: str = "./data/uploads"
    generated_dir: str = "./data/generated"
    session_hours: int = 8
    cookie_secure: bool = False
    bootstrap_email: str = "builder@liquidsoftware.local"
    bootstrap_password: str = ""
    max_upload_bytes: int = 5_242_880
    login_max_failures: int = 5
    lock_minutes: int = 15
    allowed_hosts: str = ""
    trust_proxy: bool = False

    @property
    def session_seconds(self) -> int:
        return max(1, self.session_hours) * 3600

    @property
    def hosts(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_hosts.split(",") if item.strip()}


def _ensure_secret(settings: Settings) -> str:
    if settings.secret_key:
        if len(settings.secret_key) < 32:
            raise RuntimeError("LIQUID_SECRET_KEY must be at least 32 characters.")
        return settings.secret_key
    if settings.env == "production":
        raise RuntimeError("Set LIQUID_SECRET_KEY before starting in production.")
    path = Path(settings.secret_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    generated = secrets.token_hex(32)
    path.write_text(generated, encoding="utf-8")
    path.chmod(0o600)
    return generated


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.secret_key = _ensure_secret(settings)
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.generated_dir).mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        raw = settings.database_url.removeprefix("sqlite:///")
        if raw and raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
    return settings
