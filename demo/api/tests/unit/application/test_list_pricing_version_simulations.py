from dataclasses import replace

import pytest

from pricing_demo.domain.pricing_versions import PricingVersionNotFound, new_draft_goals
from pricing_demo.domain.runs import RunState
from pricing_demo.domain.traveller_simulation import BalancedScore, SimulationRule
from tests.support.builds import MemoryBuilds
from tests.support.pricing_versions import sealed_pricing_version
from tests.support.runs import T0
from tests.support.simulations import simulate_under

VERSION = "geneva-3km.v1"
PERIOD = f"{VERSION}.mon-08"
V1 = BalancedScore()
V2 = BalancedScore(0.6, 0.4, rule_version=2)


def rig_with_two_rules() -> tuple[MemoryBuilds, str]:
    rig = MemoryBuilds()
    version = rig.pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id
    sealed_pricing_version(rig, version, RunState.SUCCEEDED)
    simulate_under(rig.simulations, version, PERIOD, V1)
    simulate_under(rig.simulations, version, PERIOD, V2)
    return rig, version


def test_each_simulation_says_whether_its_rule_is_the_current_one() -> None:
    rig, version = rig_with_two_rules()
    rig.status.value = replace(rig.status.value, simulation_rule=SimulationRule.of(V2))

    items = rig.list_simulations.execute(version)

    assert [(item.linked.price_scheme, item.linked.rule_version) for item in items] == [
        ("flat", 1),
        ("flat", 2),
        ("model_prices", 1),
        ("model_prices", 2),
    ]
    assert [item.rule_current for item in items] == [False, True, False, True]
    assert items[1].linked.rule_parameters == {"price_weight": 0.6, "time_weight": 0.4}


def test_the_same_version_with_other_parameters_is_not_current() -> None:
    rig, version = rig_with_two_rules()
    rig.status.value = replace(
        rig.status.value, simulation_rule=SimulationRule.of(BalancedScore(0.7, 0.3, rule_version=2))
    )

    assert not any(item.rule_current for item in rig.list_simulations.execute(version))


def test_no_simulation_is_current_without_a_live_worker() -> None:
    rig, version = rig_with_two_rules()

    items = rig.list_simulations.execute(version)

    assert len(items) == 4
    assert not any(item.rule_current for item in items)


def test_a_version_without_simulations_has_an_empty_list() -> None:
    rig = MemoryBuilds()
    version = rig.pricing.create_draft(VERSION, None, new_draft_goals(None), PERIOD, None, T0).id

    assert rig.list_simulations.execute(version) == []


def test_an_unknown_version_is_not_found() -> None:
    with pytest.raises(PricingVersionNotFound):
        MemoryBuilds().list_simulations.execute("geneva-3km.v1.Q")
