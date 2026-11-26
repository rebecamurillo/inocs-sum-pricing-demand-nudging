import pytest
from pydantic import ValidationError

from pricing_demo.interface.http.schemas import PricingModelSettings


@pytest.mark.parametrize("step", ["area", "hubs", "routes", "travellers_and_bikes"])
def test_each_build_step_can_be_failed_and_held(step: str) -> None:
    settings = PricingModelSettings.model_validate(
        {"fail_at": {"step": step, "code": "stage_error"}, "hold_at": step}
    )

    assert settings.model_dump(mode="json")["hold_at"] == step


@pytest.mark.parametrize(
    "body",
    [
        {"fail_at": {"step": "pricing_model", "code": "stage_error"}},
        {"hold_at": "traveller_simulation"},
    ],
)
def test_a_step_the_fake_pricing_model_does_not_play_is_refused(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PricingModelSettings.model_validate(body)
