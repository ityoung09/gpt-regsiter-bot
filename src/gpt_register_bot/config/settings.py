from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GPT_REGISTER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", description="Web server bind host")
    port: int = Field(default=8000, ge=1, le=65535, description="Web server port")
    project_root: Path = Field(default_factory=_default_project_root)
    output_dir: Path | None = None
    max_log_lines: int = Field(default=2500, ge=100)
    max_log_tail: int = Field(default=600, ge=50)
    default_concurrency: int = Field(default=3, ge=1, le=32)
    default_provider: str = Field(default="mailtm")

    @model_validator(mode="after")
    def _apply_defaults(self) -> Settings:
        if self.output_dir is None:
            self.output_dir = self.project_root / "output"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
