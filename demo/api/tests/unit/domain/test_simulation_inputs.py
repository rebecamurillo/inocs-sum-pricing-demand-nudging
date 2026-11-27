import pytest

from pricing_demo.domain.read_model import HubPairRow, RouteOptionRow
from pricing_demo.domain.simulation_inputs import simulation_instance_from
from pricing_demo.domain.solves import SolveRow, model_bike_prices


def option(arc: str, mode: str, **fields: object) -> RouteOptionRow:
    return RouteOptionRow(arc, "A", "B", mode, 600.0, 60.0, 1000.0, (), [], **fields)  # type: ignore[arg-type]


def test_the_instance_has_whole_travellers_and_the_options_with_their_prices_parts() -> None:
    instance = simulation_instance_from(
        [HubPairRow("A", "B", 12.0, 800.0)],
        [
            option("1b", "pt_bike", bike_legs=2),
            option("2p", "pt_only", bike_legs=0),
            option("3c", "car", bike_legs=0, car_cost_chf=4.0, parking_time_min=3.0),
        ],
        [],
        [],
    )

    assert [
        (pair.origin_hub, pair.destination_hub, pair.travellers) for pair in instance.pairs
    ] == [("A", "B", 12)]
    assert isinstance(instance.pairs[0].travellers, int)
    assert [(item.arc_id, item.mode, item.bike_legs) for item in instance.options] == [
        ("1b", "pt_bike", 2),
        ("2p", "pt_only", 0),
        ("3c", "car", 0),
    ]
    assert (instance.options[2].car_cost_chf, instance.options[2].parking_time_min) == (4.0, 3.0)


def test_a_bike_option_without_its_count_of_legs_raises() -> None:
    with pytest.raises(ValueError, match="1b"):
        simulation_instance_from([], [option("1b", "pt_bike")], [], [])


def test_a_car_option_without_its_cost_raises() -> None:
    with pytest.raises(ValueError, match="3c"):
        simulation_instance_from([], [option("3c", "car", bike_legs=0)], [], [])


def test_the_model_prices_are_the_bike_prices_of_the_bike_rows_only() -> None:
    rows = [
        SolveRow("1b", "A", "B", "PT+Bike", 1, 2, 1.5, 3.5, 0, 0),
        SolveRow("2p", "A", "B", "PT-Only", 1, 2, None, 2.0, 0, 0),
        SolveRow("3c", "A", "B", "Car", 1, 2, 9.0, 6.0, 0, 0),
    ]

    assert model_bike_prices(rows) == {"1b": 1.5}
