from dataclasses import replace
from typing import Any

import pytest

from pricing_demo.domain.comparison import (
    BEST_DIRECTIONS,
    ComparedVersion,
    ComparisonGroup,
    DifferentInstances,
    VersionCountOutOfRange,
    best_letters,
    check_version_count,
    comparison_groups,
    derived_hub_differences,
    derived_pair_differences,
    flat_references,
    goal_numbers,
    identical_solve_groups,
)
from pricing_demo.domain.derived_result import (
    HubNumbers,
    PairNumbers,
    ResultNumbers,
    SimulationSummary,
)
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import GOAL_NAMES, new_draft_goals


def num(value: float, unit: str = "travellers", source: Any = "model") -> Number:
    return Number(value, unit, source, "headline")


def summary(key: str = "flat-1", **changes: Any) -> SimulationSummary:
    values: dict[str, Any] = {
        "key": key,
        "price_scheme": "flat",
        "rule_id": "balanced-score",
        "rule_version": 1,
        "rule_parameters": {"price_weight": 0.5},
        "travellers": 20,
        "travellers_per_mode": {"pt_bike": 5, "pt_only": 5, "car": 10},
        "displaced": 1,
        "unserved": 0,
        "bike_rides": 10,
        "bike_revenue_chf": 10.0,
        "stations_empty": 2,
        "stations_full": 1,
    }
    values.update(changes)
    return SimulationSummary(**values)


def pair(origin: str, dest: str, mean: float | None, riders: float) -> PairNumbers:
    return PairNumbers(
        origin,
        dest,
        {"pt_bike": num(riders), "pt_only": num(0), "car": num(0)},
        None if mean is None else num(mean, "chf_per_bike_leg", "derived"),
        None,
        None,
    )


def hub(hub_id: str, mean: float | None, rides: float) -> HubNumbers:
    return HubNumbers(
        hub_id,
        num(rides, "bike_rides", "derived"),
        num(0, "bike_rides", "derived"),
        None if mean is None else num(mean, "chf_per_bike_leg", "derived"),
    )


def result(**numbers: float) -> ResultNumbers:
    base = {
        "ridership": 10.0,
        "modal_split_car": 0.4,
        "modal_split_pt_only": 0.3,
        "modal_split_pt_bike": 0.3,
        "profit": 5.0,
        "revenue": 9.0,
        "cost": 4.0,
        "mean_bike_price": 1.0,
        "rides_under_cost": 1.0,
        "stations_empty_end": 1.0,
        "stations_full_end": 1.0,
        "hub_pairs_with_bike_option": 2.0,
    }
    base.update(numbers)
    model = {"ridership", "modal_split_car", "modal_split_pt_only", "modal_split_pt_bike"}
    return ResultNumbers(
        {
            name: num(
                value, "x", "model" if name in model or name.startswith("hub_") else "derived"
            )
            for name, value in base.items()
        },
        (),
        (),
        None,
        None,
    )


def version(letter: str, **changes: Any) -> ComparedVersion:
    values: dict[str, Any] = {
        "letter": letter,
        "goals": new_draft_goals(None),
        "numbers": result(),
        "model_prices": summary(f"model-{letter}", price_scheme="model_prices"),
        "flat": summary(),
        "flat_rule_current": True,
        "solve_key": f"solve-{letter}",
        "advanced": {"objective_value": Number(1.0, "objective", "model", "advanced")},
        "bike_options_offered": 3,
    }
    values.update(changes)
    return ComparedVersion(**values)


def group(groups: tuple[ComparisonGroup, ...], name: str) -> dict[str, Any]:
    found = next(item for item in groups if item.name == name)
    return {row.key: row for row in found.rows}


def test_the_count_check_accepts_two_to_four_only() -> None:
    for count in (2, 3, 4):
        check_version_count(count)
    for count in (0, 1, 5):
        with pytest.raises(VersionCountOutOfRange):
            check_version_count(count)


def test_the_errors_say_what_they_are() -> None:
    assert "5" in str(VersionCountOutOfRange(5))
    assert "a" in str(DifferentInstances(["a", "b"]))


def test_best_value_follows_the_direction_of_the_row() -> None:
    values = {"A": num(3), "B": num(5), "C": None}
    assert best_letters(values, "lowest") == ("A",)
    assert best_letters(values, "highest") == ("B",)


def test_an_equal_row_has_no_best_value_and_a_tie_marks_every_tied_version() -> None:
    assert best_letters({"A": num(3), "B": num(3)}, "lowest") == ()
    assert best_letters({"A": num(3), "B": num(7), "C": num(3)}, "lowest") == ("A", "C")
    assert best_letters({"A": num(3), "B": None}, "lowest") == ()


def test_only_the_four_marked_rows_have_a_best_value_in_each_group_where_they_exist() -> None:
    a = version(
        "A",
        numbers=result(ridership=12, profit=9, stations_empty_end=0, modal_split_car=0.2),
        model_prices=summary(
            "m-a",
            travellers_per_mode={"pt_bike": 8, "pt_only": 6, "car": 6},
            bike_revenue_chf=20.0,
            stations_empty=0,
            stations_full=0,
            displaced=0,
        ),
    )
    b = version("B")
    references = flat_references([a, b])
    groups = comparison_groups([a, b], references)

    simulated = group(groups, "simulated")
    assert simulated["share_car"].best == ("A",)
    assert simulated["ridership"].best == ("A",)
    assert simulated["profit"].best == ("A",)
    assert simulated["stations_empty_or_full"].best == ("A",)
    assert simulated["displaced"].best == ()
    assert simulated["mean_bike_price"].best == ()
    assert group(groups, "model")["share_car"].best == ("A",)
    assert group(groups, "model")["ridership"].best == ("A",)
    assert group(groups, "model")["bike_price_min"].best == ()
    derived = group(groups, "derived")
    assert derived["profit"].best == ("A",)
    assert derived["stations_empty_or_full"].best == ("A",)
    assert derived["revenue"].best == ()
    for name in ("simulated", "model", "derived", "goals_that_differ", "solver"):
        for row in group(groups, name).values():
            assert set(row.best) <= {"A", "B"}
            assert row.key in BEST_DIRECTIONS or row.best == ()


def test_the_same_key_is_judged_separately_in_each_group() -> None:
    a = version("A", numbers=result(profit=1.0))
    b = version("B", numbers=result(profit=9.0))
    groups = comparison_groups([a, b], flat_references([a, b]))
    assert group(groups, "derived")["profit"].best == ("B",)
    assert group(groups, "simulated")["profit"].best == ()


def test_the_groups_come_in_order_with_one_source_per_row() -> None:
    a, b = version("A"), version("B")
    groups = comparison_groups([a, b], flat_references([a, b]))
    assert [item.name for item in groups] == [
        "simulated",
        "model",
        "derived",
        "goals_that_differ",
        "solver",
    ]
    expected = {"simulated": "simulation", "model": "model", "derived": "derived"}
    for name, source in expected.items():
        for row in group(groups, name).values():
            sources = {item.source for item in row.values.values() if item is not None}
            assert sources <= {source}, (name, row.key)
    for row in group(groups, "solver").values():
        assert {item.group for item in row.values.values() if item is not None} <= {"advanced"}


def test_flat_columns_never_win_and_carry_their_own_values() -> None:
    a = version("A")
    b = version("B", flat=summary("flat-2", bike_revenue_chf=1.0))
    references = flat_references([a, b])
    simulated = group(comparison_groups([a, b], references), "simulated")
    assert set(simulated["profit"].flats) == {"flat-1", "flat-2"}
    assert set(simulated["profit"].best) <= {"A", "B"}
    assert simulated["profit"].flats["flat-2"] is not None


def test_changes_are_the_model_prices_minus_the_flat_simulation_in_points_for_shares() -> None:
    a = version(
        "A",
        model_prices=summary("m-a", travellers_per_mode={"pt_bike": 10, "pt_only": 5, "car": 5}),
    )
    b = version("B")
    simulated = group(comparison_groups([a, b], flat_references([a, b])), "simulated")
    car = simulated["share_car"].changes["A"]
    assert car.unit == "share_points"
    assert car.value == pytest.approx(-25.0)
    assert simulated["ridership"].changes["A"].value == 5
    assert simulated["ridership"].changes["B"].value == 0


def test_versions_with_the_same_flat_simulation_share_one_reference() -> None:
    references = flat_references([version("A"), version("B")])
    assert len(references) == 1
    assert references[0].letters == ("A", "B")
    assert references[0].id == "flat-1"
    assert references[0].rule_current is True
    assert set(references[0].values) == {
        "flat_price_per_ride_chf",
        "pt_fare_chf",
        "car_parking_fee_chf",
    }


@pytest.mark.parametrize("change", ["flat", "fare", "parking"])
def test_a_different_flat_price_fare_or_parking_fee_gives_its_own_reference(change: str) -> None:
    goals = new_draft_goals(None)
    other = {
        "flat": goals.replacing({"flat_price_per_ride_chf": 2.5}),
        "fare": goals.replacing({"pt_fare_chf": 9.0}),
        "parking": goals.replacing({"car_parking_fee_chf": 9.0}),
    }[change]
    references = flat_references(
        [version("A"), version("B", goals=other, flat=summary("flat-other"))]
    )
    assert [item.letters for item in references] == [("A",), ("B",)]
    assert references[1].values["flat_price_per_ride_chf"].value == float(
        other.flat_price_per_ride_chf
    )


def test_a_flat_simulation_under_an_older_rule_gets_its_own_reference() -> None:
    older = version("B", flat=summary("flat-old", rule_version=0), flat_rule_current=False)
    references = flat_references([version("A"), older])
    assert [item.letters for item in references] == [("A",), ("B",)]
    assert (references[0].rule_current, references[1].rule_current) == (True, False)
    assert references[1].rule_version == 0


def test_identical_solves_are_the_versions_sharing_a_solve_key() -> None:
    versions = [
        version("A", solve_key="s1"),
        version("B", solve_key="s2"),
        version("C", solve_key="s1"),
    ]
    assert identical_solve_groups(versions) == (("A", "C"),)
    assert identical_solve_groups([version("A"), version("B")]) == ()


def test_pairs_are_ordered_by_the_absolute_price_difference_then_the_hubs() -> None:
    a = version(
        "A",
        numbers=replace(
            result(),
            pairs=(
                pair("h1", "h2", 1.0, 4),
                pair("h1", "h3", 1.0, 4),
                pair("h2", "h3", 1.0, 4),
                pair("h3", "h4", 1.0, 4),
                pair("h4", "h5", None, 0),
            ),
        ),
    )
    b = version(
        "B",
        numbers=replace(
            result(),
            pairs=(
                pair("h1", "h2", 1.5, 6),
                pair("h1", "h3", 0.5, 2),
                pair("h2", "h3", 1.0, 4),
                pair("h3", "h4", None, 0),
                pair("h4", "h5", 3.0, 1),
            ),
        ),
    )
    found = derived_pair_differences(a, b)
    assert [(item.origin_hub, item.destination_hub) for item in found] == [
        ("h1", "h2"),
        ("h1", "h3"),
        ("h2", "h3"),
    ]
    first = found[0]
    assert first.price_difference.value == pytest.approx(0.5)
    assert first.price_difference.source == "derived"
    assert (first.travellers_a.value, first.travellers_b.value) == (4, 6)
    assert first.travellers_difference.value == 2


def test_versions_sharing_a_solve_list_no_pair() -> None:
    numbers = replace(result(), pairs=(pair("h1", "h2", 1.0, 4),))
    a = version("A", numbers=numbers, solve_key="same")
    b = version("B", numbers=numbers, solve_key="same")
    assert derived_pair_differences(a, b) == ()


def test_hub_differences_carry_both_means_the_flat_gap_and_the_rides() -> None:
    a = version("A", numbers=replace(result(), hubs=(hub("h1", 1.0, 3), hub("h2", None, 0))))
    b_goals = new_draft_goals(None).replacing({"flat_price_per_ride_chf": 1.0})
    b = version(
        "B", goals=b_goals, numbers=replace(result(), hubs=(hub("h1", 1.5, 5), hub("h2", 2.0, 1)))
    )
    first, second = derived_hub_differences(a, b)
    assert first.hub_id == "h1"
    assert first.price_difference is not None
    assert first.price_difference.value == 0.5
    assert first.price_b_minus_flat is not None
    assert first.price_b_minus_flat.value == 0.5
    assert first.rides_starting_difference is not None
    assert first.rides_starting_difference.value == 2
    assert second.mean_price_a is None
    assert second.price_difference is None
    assert second.mean_price_b is not None


def test_goals_that_differ_lists_only_goals_with_different_values() -> None:
    a = version("A")
    b = version("B", goals=a.goals.replacing({"ridership_weight": 9.0}))
    rows = group(comparison_groups([a, b], flat_references([a, b])), "goals_that_differ")
    assert list(rows) == ["ridership_weight"]
    assert rows["ridership_weight"].values["B"].source == "input"
    same = group(comparison_groups([a, a], flat_references([a, a])), "goals_that_differ")
    assert same == {}


def test_the_eight_goals_are_inputs_with_their_units() -> None:
    goals = goal_numbers(new_draft_goals(None))
    assert tuple(goals) == GOAL_NAMES
    assert {item.source for item in goals.values()} == {"input"}
    assert goals["pt_fare_chf"].unit == "chf"
    assert goals["ridership_weight"].unit == "none"
    assert goals["max_displayed_options"].unit == "none"


def test_the_solver_terms_row_exists_only_when_a_version_has_terms() -> None:
    a, b = version("A"), version("B")
    rows = group(comparison_groups([a, b], flat_references([a, b])), "solver")
    assert "objective_term_revenue" not in rows
    with_terms = version(
        "A", advanced={"objective_term_revenue": Number(2.0, "objective", "derived", "advanced")}
    )
    rows = group(comparison_groups([with_terms, b], flat_references([with_terms, b])), "solver")
    assert rows["objective_term_revenue"].values["B"] is None
    assert rows["bike_options_offered"].values["A"].value == 3
