from pricing_demo.domain.traveller_simulation import BalancedScore, SimulationRule


def test_a_rule_is_built_from_the_rule_that_simulates_and_records_the_workers_row_shape() -> None:
    rule = SimulationRule.of(BalancedScore())

    assert rule == SimulationRule("balanced-score", 1, {"price_weight": 0.5, "time_weight": 0.5})
    assert rule.record() == {
        "id": "balanced-score",
        "version": 1,
        "parameters": {"price_weight": 0.5, "time_weight": 0.5},
    }


def test_a_record_gives_the_rule_back() -> None:
    staged = SimulationRule.of(BalancedScore(0.6, 0.4, rule_version=2))

    assert SimulationRule.from_record(staged.record()) == staged


def test_two_rules_are_equal_when_the_triple_is_equal() -> None:
    assert SimulationRule("balanced-score", 1, {"a": 1}) == SimulationRule(
        "balanced-score", 1, {"a": 1.0}
    )
    assert SimulationRule("balanced-score", 1, {"a": 1}) != SimulationRule(
        "balanced-score", 2, {"a": 1}
    )
    assert SimulationRule("balanced-score", 1, {"a": 1}) != SimulationRule(
        "balanced-score", 1, {"a": 0.5}
    )
    assert SimulationRule("balanced-score", 1, {"a": 1}) != SimulationRule("other", 1, {"a": 1})


def test_a_malformed_or_absent_record_is_no_rule() -> None:
    assert SimulationRule.from_record(None) is None
    assert SimulationRule.from_record({}) is None
    assert SimulationRule.from_record({"id": "x", "version": "1", "parameters": {}}) is None
    assert SimulationRule.from_record({"id": "x", "version": 1, "parameters": []}) is None
    assert SimulationRule.from_record({"id": "x", "version": 1, "parameters": {"a": "b"}}) is None
    assert SimulationRule.from_record({"id": 3, "version": 1, "parameters": {}}) is None


def test_a_record_that_is_not_an_object_or_holds_a_number_beyond_a_float_is_no_rule() -> None:
    # The jsonb column accepts any JSON value; /system-status must not fail on one.
    assert SimulationRule.from_record([1]) is None  # type: ignore[arg-type]
    assert SimulationRule.from_record("x") is None  # type: ignore[arg-type]
    assert SimulationRule.from_record(5) is None  # type: ignore[arg-type]
    assert (
        SimulationRule.from_record({"id": "x", "version": 1, "parameters": {"a": 10**400}}) is None
    )
