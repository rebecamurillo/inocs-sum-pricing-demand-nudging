import pytest

from pricing_demo.domain.pricing_versions import (
    DEFAULT_GOALS,
    FALLBACK_KEPT,
    PricingGoals,
    SealedWithoutRun,
    city_instance_of,
    duplicated_goals,
    instance_version_of,
    new_draft_goals,
    pricing_letter,
    pricing_version_id,
    pricing_version_state,
)
from pricing_demo.domain.runs import RunState


def _goals(**changes: float) -> PricingGoals:
    return new_draft_goals(None).replacing(changes)


@pytest.mark.parametrize(
    ("index", "letter"),
    [(0, "A"), (1, "B"), (25, "Z"), (26, "AA"), (27, "AB"), (51, "AZ"), (52, "BA"), (701, "ZZ")],
)
def test_letters_follow_the_spreadsheet_order(index: int, letter: str) -> None:
    assert pricing_letter(index) == letter


def test_the_id_of_a_pricing_version() -> None:
    assert pricing_version_id("geneva-3km.v1", "C") == "geneva-3km.v1.C"


def test_the_instance_version_and_the_city_instance_are_read_off_a_pricing_version_id() -> None:
    assert instance_version_of("geneva-3km.v1.B") == "geneva-3km.v1"
    assert city_instance_of("geneva-3km.v1") == "geneva-3km"
    assert city_instance_of(instance_version_of("geneva-3km.v12.AB")) == "geneva-3km"


def test_a_first_draft_takes_the_provisional_goals_and_the_fallback_kept_values() -> None:
    goals = new_draft_goals(None)

    assert (goals.cost_bike_chf, goals.lowest_price_chf) == (0.60, 0.60)
    assert (goals.ridership_weight, goals.station_balance_weight) == (8.0, 0.5)
    assert (goals.pt_fare_chf, goals.car_parking_fee_chf) == (2.0, 2.8)
    assert (goals.max_displayed_options, goals.flat_price_per_ride_chf) == (10, 1.00)
    assert goals.flat_price_kind == "per_ride"
    assert (DEFAULT_GOALS, FALLBACK_KEPT) == ((0.60, 0.60, 8.0, 0.5), (2.0, 2.8, 10, 1.00))


def test_a_later_draft_keeps_four_values_of_the_last_sealed_version() -> None:
    sealed = _goals(
        pt_fare_chf=2.2,
        car_parking_fee_chf=3.0,
        max_displayed_options=4,
        flat_price_per_ride_chf=1.5,
        ridership_weight=99,
    )

    goals = new_draft_goals(sealed)

    assert (goals.pt_fare_chf, goals.car_parking_fee_chf) == (2.2, 3.0)
    assert (goals.max_displayed_options, goals.flat_price_per_ride_chf) == (4, 1.5)
    assert goals.ridership_weight == 8.0  # the four goals start from the defaults again


def test_a_duplicate_copies_the_eight_goal_values() -> None:
    source = PricingGoals(1, 2, 3, 4, 5, 6, 7, 8)

    assert duplicated_goals(source) == source


@pytest.mark.parametrize(
    ("status", "run", "state"),
    [
        ("draft", None, "draft"),
        ("sealed", RunState.QUEUED, "queued"),
        ("sealed", RunState.RUNNING, "running"),
        ("sealed", RunState.FAILED, "failed"),
        ("sealed", RunState.CANCELLED, "cancelled"),
        ("sealed", RunState.SUCCEEDED, "result"),
    ],
)
def test_the_state_comes_from_the_status_and_the_last_run(
    status: str, run: RunState | None, state: str
) -> None:
    assert pricing_version_state(status, run, "g.v1.A") == state  # type: ignore[arg-type]


def test_a_sealed_version_without_a_run_is_a_fault() -> None:
    with pytest.raises(SealedWithoutRun):
        pricing_version_state("sealed", None, "g.v1.A")
