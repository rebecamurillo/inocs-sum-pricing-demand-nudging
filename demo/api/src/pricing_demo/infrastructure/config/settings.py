from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting of the API and the worker, read from `PRICING_DEMO_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="PRICING_DEMO_")

    database_url: str = "postgresql+psycopg://pricing_demo:pricing_demo@localhost:5440/pricing_demo"
    adapters: Literal["fake", "real"] = "real"
    otp_url: str = "http://localhost:8080/otp/gtfs/v1"
    # Where the worker keeps its working directories and artefacts (relative to its own cwd).
    data_dir: Path = Path("var/data")
    # The worker's identity; None means "{host}-{pid}".
    worker_id: str | None = None

    @field_validator("worker_id")
    @classmethod
    def _empty_worker_id_is_unset(cls, value: str | None) -> str | None:
        return value or None
