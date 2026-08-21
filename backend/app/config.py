from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://autostream:autostream@localhost:5432/autostream"
    fixtures_dir: Path = Path(__file__).resolve().parents[2] / "fixtures"
    nhtsa_fixture_dir: Path | None = None
    app_env: str = "development"
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_fixtures_dir() -> Path:
    return get_settings().fixtures_dir.resolve()
