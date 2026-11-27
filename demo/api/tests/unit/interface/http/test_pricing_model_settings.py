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


def test_route_failures_are_accepted_and_default_to_none() -> None:
    assert PricingModelSettings.model_validate({}).route_failures == []
    settings = PricingModelSettings.model_validate(
        {
            "route_failures": [
                {
                    "origin_hub": "H1",
                    "destination_hub": "H2",
                    "query": "pt_bike",
                    "kind": "technical",
                    "message": "timeout",
                }
            ]
        }
    )

    assert settings.model_dump(mode="json")["route_failures"][0]["query"] == "pt_bike"


@pytest.mark.parametrize(("field", "value"), [("query", "walk"), ("kind", "slow")])
def test_a_route_failure_naming_an_unknown_query_or_kind_is_refused(field: str, value: str) -> None:
    failure = {
        "origin_hub": "H1",
        "destination_hub": "H2",
        "query": "car",
        "kind": "no_route",
        "message": "m",
        field: value,
    }

    with pytest.raises(ValidationError):
        PricingModelSettings.model_validate({"route_failures": [failure]})
