from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting of the API, read from `PRICING_DEMO_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="PRICING_DEMO_")

    database_url: str = "postgresql+psycopg://pricing_demo:pricing_demo@localhost:5440/pricing_demo"
    adapters: Literal["fake", "real"] = "real"
    otp_url: str = "http://localhost:8080/otp/gtfs/v1"
