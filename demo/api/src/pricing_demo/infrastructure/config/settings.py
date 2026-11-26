from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# `demo/`, and the default inputs of the city data import.
DEMO_DIR = Path(__file__).resolve().parents[5]
DEFAULT_GTFS = (
    DEMO_DIR.parent
    / "Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/tpg_gtfs.zip"
)
DEFAULT_OSM_DIR = DEMO_DIR / "otp/data"
# pfaedle, the tool that draws the bus legs on the streets; the digest of
# `ghcr.io/ad-freiburg/pfaedle:latest` on 2026-11-26.
_PFAEDLE_DIGEST = "sha256:af4fdc647699ea1ffe5150fd1f9d264c465c2876710ea749e8cb284f13abd20d"
DEFAULT_SHAPE_TOOL_IMAGE = f"ghcr.io/ad-freiburg/pfaedle@{_PFAEDLE_DIGEST}"


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
    # The Docker image the city data import runs to draw the bus legs on the streets.
    shape_tool_image: str = DEFAULT_SHAPE_TOOL_IMAGE
    # How often the worker probes the solver, the package and the trip planner and reports them.
    component_report_interval_s: float = Field(default=30.0, gt=0)

    @field_validator("worker_id")
    @classmethod
    def _empty_worker_id_is_unset(cls, value: str | None) -> str | None:
        return value or None
