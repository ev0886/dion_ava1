from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DION_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "DION ABA1"
    app_environment: str = "development"
    data_dir: Path = Field(default=Path("var"))
    sqlite_filename: str = "dion_aba1.sqlite3"
    alembic_config_path: Path = Field(default=Path("alembic.ini"))

    @property
    def sqlite_path(self) -> Path:
        return self.data_dir / self.sqlite_filename

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.sqlite_path.as_posix()}"


def get_settings() -> AppSettings:
    return AppSettings()
