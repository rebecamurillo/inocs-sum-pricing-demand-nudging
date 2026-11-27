from pathlib import Path

import pytest

from pricing_demo.infrastructure.config.settings import (
    DEFAULT_OTP_GRAPH_DIR,
    DEFAULT_SHAPE_TOOL_IMAGE,
    DEMO_DIR,
    Settings,
)


def test_the_defaults_point_at_the_local_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DATABASE_URL",
        "ADAPTERS",
        "OTP_URL",
        "DATA_DIR",
        "WORKER_ID",
        "COMPONENT_REPORT_INTERVAL_S",
        "SHAPE_TOOL_IMAGE",
        "OTP_GRAPH_DIR",
    ):
        monkeypatch.delenv(f"PRICING_DEMO_{name}", raising=False)

    settings = Settings()

    assert settings.database_url == (
        "postgresql+psycopg://pricing_demo:pricing_demo@localhost:5440/pricing_demo"
    )
    assert settings.adapters == "real"
    assert settings.otp_url == "http://localhost:8080/otp/gtfs/v1"
    assert settings.data_dir == Path("var/data")
    assert settings.worker_id is None
    assert settings.component_report_interval_s == 30
    assert settings.shape_tool_image == DEFAULT_SHAPE_TOOL_IMAGE
    assert settings.otp_graph_dir == DEFAULT_OTP_GRAPH_DIR == DEMO_DIR / "otp/data"
    assert settings.otp_graph_dir.is_absolute()


def test_settings_come_from_prefixed_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRICING_DEMO_ADAPTERS", "fake")
    monkeypatch.setenv("PRICING_DEMO_OTP_URL", "http://otp:8080/otp/gtfs/v1")
    monkeypatch.setenv("PRICING_DEMO_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")

    settings = Settings()

    assert settings.adapters == "fake"
    assert settings.otp_url == "http://otp:8080/otp/gtfs/v1"
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/x"


def test_the_graph_folder_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PRICING_DEMO_OTP_GRAPH_DIR", str(tmp_path))

    assert Settings().otp_graph_dir == tmp_path


def test_an_unknown_adapter_set_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRICING_DEMO_ADAPTERS", "mock")

    with pytest.raises(ValueError, match="adapters"):
        Settings()


def test_the_data_directory_and_the_worker_id_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRICING_DEMO_DATA_DIR", "/srv/lab")
    monkeypatch.setenv("PRICING_DEMO_WORKER_ID", "w-1")

    settings = Settings()

    assert settings.data_dir == Path("/srv/lab")
    assert settings.worker_id == "w-1"


def test_an_empty_worker_id_reads_as_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRICING_DEMO_WORKER_ID", "")

    assert Settings().worker_id is None


def test_the_component_report_interval_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRICING_DEMO_COMPONENT_REPORT_INTERVAL_S", "1")

    assert Settings().component_report_interval_s == 1


def test_a_component_report_interval_of_zero_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRICING_DEMO_COMPONENT_REPORT_INTERVAL_S", "0")

    with pytest.raises(ValueError, match="greater than 0"):
        Settings()


def test_the_shape_tool_image_is_pinned_by_digest_and_can_be_overridden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert DEFAULT_SHAPE_TOOL_IMAGE == (
        "ghcr.io/ad-freiburg/pfaedle"
        "@sha256:af4fdc647699ea1ffe5150fd1f9d264c465c2876710ea749e8cb284f13abd20d"
    )
    monkeypatch.setenv("PRICING_DEMO_SHAPE_TOOL_IMAGE", "example/pfaedle:2")

    assert Settings().shape_tool_image == "example/pfaedle:2"


def test_the_trip_planner_retries_and_workers_default_and_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("OTP_RETRIES", "OTP_RETRY_WAIT_S", "OTP_WORKERS"):
        monkeypatch.delenv(f"PRICING_DEMO_{name}", raising=False)

    settings = Settings()
    assert (settings.otp_retries, settings.otp_retry_wait_s, settings.otp_workers) == (3, 2.0, 4)

    monkeypatch.setenv("PRICING_DEMO_OTP_RETRIES", "0")
    monkeypatch.setenv("PRICING_DEMO_OTP_RETRY_WAIT_S", "0.5")
    monkeypatch.setenv("PRICING_DEMO_OTP_WORKERS", "8")
    settings = Settings()
    assert (settings.otp_retries, settings.otp_retry_wait_s, settings.otp_workers) == (0, 0.5, 8)
