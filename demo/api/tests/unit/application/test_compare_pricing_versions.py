from dataclasses import replace
from pathlib import Path

import pytest

from pricing_demo.domain.comparison import DifferentInstances, VersionCountOutOfRange
from pricing_demo.domain.pricing_versions import NoResult, PricingVersionNotFound
from pricing_demo.domain.traveller_simulation import BalancedScore
from tests.support.results import PERIOD, ResultRig


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_two_finished_versions_are_compared_with_the_top_level_facts(rig: ResultRig) -> None:
    a, b = rig.finished(), rig.finished(cost_bike_chf=0.7)

    comparison = rig.compare.execute([a, b], None)

    assert comparison.instance_version_id == "geneva-3km.v1"
    assert comparison.instance_version_name == "Geneva 3 km v1"
    assert comparison.period_id == PERIOD
    assert comparison.period_name
    assert [item.version.letter for item in comparison.versions] == ["A", "B"]
    assert [item.version.id for item in comparison.versions] == [a, b]
    assert comparison.pair_difference_letters == ("A", "B")
    assert [item.name for item in comparison.groups] == [
        "simulated",
        "model",
        "derived",
        "goals_that_differ",
        "solver",
    ]
    assert [item.result.simulations[0].link.price_scheme for item in comparison.versions] == [
        "model_prices",
        "model_prices",
    ]
    assert all(item.package_fingerprint for item in comparison.versions)
    goals = {row.key for row in comparison.groups[3].rows}
    assert goals == {"cost_bike_chf"}


def test_four_versions_come_in_letter_order_whatever_the_given_order(rig: ResultRig) -> None:
    ids = [rig.finished(cost_bike_chf=0.5 + 0.1 * index) for index in range(4)]

    comparison = rig.compare.execute([ids[2], ids[0], ids[3], ids[1]], PERIOD)

    assert [item.version.letter for item in comparison.versions] == ["A", "B", "C", "D"]
    assert comparison.pair_difference_letters == ("C", "D")
    row = comparison.groups[0].rows[0]
    assert set(row.values) == {"A", "B", "C", "D"}


def test_versions_differing_only_by_the_flat_price_share_their_solve(rig: ResultRig) -> None:
    a = rig.finished()
    b = rig.finished(flat_price_per_ride_chf=2.5)

    comparison = rig.compare.execute([a, b], None)

    assert comparison.identical_solves == (("A", "B"),)
    assert [row.key for row in comparison.groups[3].rows] == ["flat_price_per_ride_chf"]
    assert comparison.pair_differences == ()
    assert len(comparison.flat_references) == 2


def test_versions_with_the_same_flat_price_share_one_reference_and_no_solve(
    rig: ResultRig,
) -> None:
    a, b = rig.finished(), rig.finished(cost_bike_chf=0.9)

    comparison = rig.compare.execute([a, b], None)

    assert len(comparison.flat_references) == 1
    assert comparison.flat_references[0].letters == ("A", "B")
    assert {item.flat_reference for item in comparison.versions} == {
        comparison.flat_references[0].id
    }
    assert comparison.identical_solves == ()


def test_a_version_simulated_under_an_older_rule_has_its_own_flat_reference(
    rig: ResultRig,
) -> None:
    a = rig.finished()
    newer = BalancedScore(0.6, 0.4, rule_version=2)
    rig.use_rule(newer)
    rig.current_rule(newer)
    b = rig.finished()

    comparison = rig.compare.execute([a, b], None)

    assert [item.letters for item in comparison.flat_references] == [("A",), ("B",)]
    assert [item.rule_current for item in comparison.flat_references] == [False, True]
    assert [
        [sim.rule_current for sim in item.result.simulations] for item in comparison.versions
    ] == [[False, False], [True, True]]


def test_the_count_is_checked_first(rig: ResultRig) -> None:
    a = rig.finished()
    with pytest.raises(VersionCountOutOfRange):
        rig.compare.execute([a], None)
    with pytest.raises(VersionCountOutOfRange):
        rig.compare.execute([a, a], None)
    ids = [rig.finished() for _ in range(4)]
    with pytest.raises(VersionCountOutOfRange):
        rig.compare.execute([*ids, a], None)
    with pytest.raises(VersionCountOutOfRange):
        rig.compare.execute(["nope"], None)


def test_an_unknown_version_is_not_found(rig: ResultRig) -> None:
    a = rig.finished()
    with pytest.raises(PricingVersionNotFound):
        rig.compare.execute([a, "geneva-3km.v1.Z"], None)


def test_versions_of_two_instance_versions_are_refused_before_their_results_are_read(
    rig: ResultRig,
) -> None:
    a = rig.finished()
    draft = rig.version()
    stored = rig.rig.pricing.get(draft)
    assert stored is not None
    rig.rig.pricing._versions[draft] = replace(stored, instance_version_id="geneva-3km.v2")

    with pytest.raises(DifferentInstances):
        rig.compare.execute([a, draft], None)


def test_a_version_without_a_result_is_refused_as_no_result(rig: ResultRig) -> None:
    a = rig.finished()
    draft = rig.version()

    with pytest.raises(NoResult) as raised:
        rig.compare.execute([a, draft], None)

    assert raised.value.version_id == draft
