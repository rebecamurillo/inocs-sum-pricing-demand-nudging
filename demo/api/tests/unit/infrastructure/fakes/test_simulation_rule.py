from pricing_demo.domain.traveller_simulation import SimulationRule
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.simulation_rule import FakeSimulationRule


def test_the_rule_is_balanced_score_version_1_without_a_staged_rule() -> None:
    settings = InMemoryFakeSettings()

    rule = FakeSimulationRule(settings).current()

    assert SimulationRule.of(rule) == SimulationRule(
        "balanced-score", 1, {"price_weight": 0.5, "time_weight": 0.5}
    )


def test_a_staged_rule_is_read_at_each_call() -> None:
    settings = InMemoryFakeSettings()
    source = FakeSimulationRule(settings)
    settings.set_pricing_model(
        {"simulation_rule": {"version": 2, "price_weight": 0.6, "time_weight": 0.4}}
    )

    rule = source.current()

    assert SimulationRule.of(rule) == SimulationRule(
        "balanced-score", 2, {"price_weight": 0.6, "time_weight": 0.4}
    )

    settings.set_pricing_model({"fail_at": {"step": "pricing_model", "code": "x"}})

    assert SimulationRule.of(source.current()).version == 1
    settings.set_pricing_model(None)
    assert SimulationRule.of(source.current()).version == 1
