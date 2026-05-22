from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    database_url: str | None = None

    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")

    @property
    def resolved_database_url(self) -> str:
        """Return the configured database URL or a stable backend-local SQLite path."""
        if self.database_url:
            return self.database_url
        db_path = Path(__file__).resolve().parents[2] / "glyco.db"
        return f"sqlite:///{db_path.as_posix()}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cache settings so imports share one environment-derived configuration."""
    return Settings()
