import pytest

from pricing_demo.infrastructure.config.settings import Settings


def test_the_defaults_point_at_the_local_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATABASE_URL", "ADAPTERS", "OTP_URL"):
        monkeypatch.delenv(f"PRICING_DEMO_{name}", raising=False)

    settings = Settings()

    assert settings.database_url == (
        "postgresql+psycopg://pricing_demo:pricing_demo@localhost:5440/pricing_demo"
    )
    assert settings.adapters == "real"
    assert settings.otp_url == "http://localhost:8080/otp/gtfs/v1"


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


def test_an_unknown_adapter_set_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRICING_DEMO_ADAPTERS", "mock")

    with pytest.raises(ValueError, match="adapters"):
        Settings()
