from dataclasses import replace

from pricing_demo.domain.read_model import StationBikesRow
from pricing_demo.domain.solve_verification import (
    ChoiceRow,
    ModeRow,
    PairRow,
    SimulationRows,
    SolveVerification,
    StationRow,
    compare_simulation_rows,
    compare_solve_rows,
    report_lines,
    simulation_rows,
)
from pricing_demo.domain.solves import SolveRow
from pricing_demo.domain.traveller_simulation import (
    BalancedScore,
    FlatPrice,
    SimulationInstance,
    SimulationOption,
    SimulationPair,
)

SCHEME = "flat (balanced-score v1)"


def solve_rows() -> list[SolveRow]:
    return [
        SolveRow("1b", "A", "B", "PT+Bike", 1.0, 4.0, 1.5, 3.5, 0.0, 0.0),
        SolveRow("2p", "A", "B", "PT-Only", 1.0, 3.0, None, 2.0, 0.0, 0.0),
    ]


def rows() -> SimulationRows:
    return SimulationRows(
        modes=(ModeRow("pt_bike", 3), ModeRow("car", 1)),
        choices=(
            ChoiceRow("A", "B", "1b", "pt_bike", 3, 3.5, 0),
            ChoiceRow("A", "B", "3c", "car", 1, 6.0, 1),
        ),
        pairs=(PairRow("A", "B", 2),),
        stations=(StationRow("s1", 4.0, False, False), StationRow("s2", 0.0, True, False)),
    )


def test_identical_solve_rows_have_no_difference() -> None:
    table = compare_solve_rows(solve_rows(), solve_rows())

    assert table.table == "solve_rows"
    assert table.compared == 2
    assert table.differences == ()
    assert table.matches


def test_a_changed_solve_field_is_one_difference_with_the_hub_pair_option_and_both_values() -> None:
    changed = [replace(solve_rows()[0], bike_price=1.6), solve_rows()[1]]

    table = compare_solve_rows(solve_rows(), changed)

    assert not table.matches
    (difference,) = table.differences
    assert (difference.table, difference.scheme) == ("solve_rows", None)
    assert difference.key == "A>B 1b"
    assert (difference.field, difference.stored, difference.rerun) == ("bike_price", 1.5, 1.6)


def test_a_solve_row_on_one_side_only_is_a_difference_with_the_other_value_missing() -> None:
    table = compare_solve_rows(solve_rows(), solve_rows()[:1])

    (difference,) = table.differences
    assert difference.key == "A>B 2p"
    assert (difference.stored, difference.rerun) == ("present", "missing")
    only_rerun = compare_solve_rows(solve_rows()[:1], solve_rows())
    assert (only_rerun.differences[0].stored, only_rerun.differences[0].rerun) == (
        "missing",
        "present",
    )


def test_identical_simulation_rows_match_in_the_four_tables() -> None:
    tables = compare_simulation_rows(SCHEME, rows(), rows())

    assert [item.table for item in tables] == [
        "simulation_modes",
        "simulation_choices",
        "simulation_pairs",
        "simulation_stations",
    ]
    assert [item.compared for item in tables] == [2, 2, 1, 2]
    assert all(item.matches and item.scheme == SCHEME for item in tables)


def only_difference(changed: SimulationRows, table: str):  # type: ignore[no-untyped-def]
    found = [
        item for item in compare_simulation_rows(SCHEME, rows(), changed) if item.table == table
    ]
    (item,) = found
    others = [x for x in compare_simulation_rows(SCHEME, rows(), changed) if x.table != table]
    assert all(x.matches for x in others)
    (difference,) = item.differences
    return difference


def test_a_changed_mode_is_keyed_by_the_mode() -> None:
    changed = replace(rows(), modes=(ModeRow("pt_bike", 2), ModeRow("car", 1)))

    difference = only_difference(changed, "simulation_modes")

    assert (difference.key, difference.field, difference.stored, difference.rerun) == (
        "pt_bike",
        "travellers",
        3,
        2,
    )


def test_a_changed_choice_is_keyed_by_hub_pair_and_option() -> None:
    changed = replace(
        rows(),
        choices=(rows().choices[0], rows().choices[1]._replace(travellers=2)),
    )

    difference = only_difference(changed, "simulation_choices")

    assert (difference.key, difference.field, difference.stored, difference.rerun) == (
        "A>B 3c",
        "travellers",
        1,
        2,
    )


def test_a_changed_pair_is_keyed_by_the_hub_pair() -> None:
    changed = replace(rows(), pairs=(PairRow("A", "B", 3),))

    difference = only_difference(changed, "simulation_pairs")

    assert (difference.key, difference.field) == ("A>B", "unserved")


def test_a_changed_station_is_keyed_by_the_station() -> None:
    changed = replace(rows(), stations=(StationRow("s1", 5.0, False, False), rows().stations[1]))

    difference = only_difference(changed, "simulation_stations")

    assert (difference.key, difference.field, difference.stored, difference.rerun) == (
        "s1",
        "bikes_end",
        4.0,
        5.0,
    )


def test_a_station_on_one_side_only_is_missing() -> None:
    changed = replace(rows(), stations=rows().stations[:1])

    difference = only_difference(changed, "simulation_stations")

    assert (difference.key, difference.stored, difference.rerun) == ("s2", "present", "missing")


def test_the_report_names_each_difference_each_table_the_durations_and_the_verdict() -> None:
    changed = [replace(solve_rows()[0], bike_price=1.6), solve_rows()[1]]
    simulated = compare_simulation_rows(
        SCHEME,
        rows(),
        replace(rows(), stations=(StationRow("s1", 5.0, False, False), *rows().stations[1:])),
    )
    verification = SolveVerification(
        (compare_solve_rows(solve_rows(), changed), *simulated),
        (("re-solve", 1.5), ("re-simulation " + SCHEME, 0.25)),
    )

    lines = report_lines("v.v1.B.mon-08", verification)

    assert lines[0] == "solve_rows [A>B 1b] bike_price: stored 1.5, re-run 1.6"
    assert f"simulation_stations {SCHEME} [s1] bikes_end: stored 4.0, re-run 5.0" in lines
    assert "solve_rows: 2 rows compared, differ" in lines
    assert f"simulation_modes {SCHEME}: 2 rows compared, match" in lines
    assert "re-solve: 1.50 s" in lines
    assert f"re-simulation {SCHEME}: 0.25 s" in lines
    assert lines[-1] == "verify v.v1.B.mon-08: differ"


def test_the_report_of_a_match_ends_with_match() -> None:
    verification = SolveVerification(
        (compare_solve_rows(solve_rows(), solve_rows()),), (("re-solve", 0.0),)
    )

    lines = report_lines("v.v1.B.mon-08", verification)

    assert verification.matches
    assert lines == (
        "solve_rows: 2 rows compared, match",
        "re-solve: 0.00 s",
        "verify v.v1.B.mon-08: match",
    )


def test_a_simulation_output_becomes_the_rows_the_store_keeps() -> None:
    instance = SimulationInstance(
        (SimulationPair("A", "B", 2),),
        (
            SimulationOption("1b", "A", "B", "pt_bike", 600, 0, 1),
            SimulationOption("2p", "A", "B", "pt_only", 900, 60),
        ),
        (StationBikesRow("s1", 5, 3),),
        (),
    )
    outputs = BalancedScore().simulate(instance, FlatPrice(1.0, 2.0, 2.8))

    found = simulation_rows(outputs)

    assert sum(item.travellers for item in found.modes) == 2
    assert [(item.origin_hub, item.destination_hub) for item in found.choices] == [
        ("A", "B")
    ] * len(found.choices)
    assert [item.station_id for item in found.stations] == ["s1"]
    assert found.stations[0].bikes_end == outputs.stations_end[0].bikes
