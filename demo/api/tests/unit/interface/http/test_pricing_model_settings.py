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
        {"fail_at": {"step": "traveller_simulation", "code": "stage_error"}},
        {"hold_at": "traveller_simulation"},
    ],
)
def test_a_step_the_fake_pricing_model_does_not_play_is_refused(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PricingModelSettings.model_validate(body)


def test_the_pricing_model_step_can_be_failed_but_not_held() -> None:
    settings = PricingModelSettings.model_validate(
        {"fail_at": {"step": "pricing_model", "code": "solver_no_solution"}}
    )

    assert settings.model_dump(mode="json")["fail_at"]["step"] == "pricing_model"
    with pytest.raises(ValidationError):
        PricingModelSettings.model_validate({"hold_at": "pricing_model"})


@pytest.mark.parametrize("kind", ["full", "limited"])
def test_a_licence_kind_is_accepted_and_defaults_to_none(kind: str) -> None:
    assert PricingModelSettings.model_validate({}).licence_kind is None
    assert PricingModelSettings.model_validate({"licence_kind": kind}).licence_kind == kind


def test_a_licence_kind_other_than_full_or_limited_is_refused() -> None:
    with pytest.raises(ValidationError):
        PricingModelSettings.model_validate({"licence_kind": "trial"})


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


def test_a_staged_rule_needs_version_2_and_weights_in_0_to_1() -> None:
    assert PricingModelSettings.model_validate({}).simulation_rule is None
    staged = {"version": 2, "price_weight": 0.6, "time_weight": 0.4}
    assert PricingModelSettings.model_validate({"simulation_rule": staged}).simulation_rule
    for bad in (
        {**staged, "version": 1},
        {**staged, "price_weight": 1.1},
        {**staged, "time_weight": -0.5},
    ):
        with pytest.raises(ValidationError):
            PricingModelSettings.model_validate({"simulation_rule": bad})
