"""The comparison of a stored solve and its simulations with their re-run
(`pricing-demo-worker verify`).

Rows are compared field by field under the key of their table; a row on one side only is a
difference with the other value `missing`. Floats are compared exactly: the same inputs give the
same result (NFR-3) and PostgreSQL's `Double` round-trips a float. Pure: no I/O.
"""

from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, NamedTuple

from pricing_demo.domain.solves import SolveRow
from pricing_demo.domain.traveller_simulation import SimulationOutputs

PRESENT = "present"
MISSING = "missing"
# The run folder of `verify` is `runs/verify-{uuid}/`: no run id has this prefix (run ids are
# UUIDs), so the collection of working directories leaves the folder of a verify that is running.
VERIFY_RUN_PREFIX = "verify-"


class ModeRow(NamedTuple):
    mode: str
    travellers: int


class ChoiceRow(NamedTuple):
    origin_hub: str
    destination_hub: str
    arc_id: str
    mode: str
    travellers: int
    price_chf: float
    displaced: int


class PairRow(NamedTuple):
    origin_hub: str
    destination_hub: str
    unserved: int


class StationRow(NamedTuple):
    station_id: str
    bikes_end: float
    empty: bool
    full: bool


@dataclass(frozen=True)
class SimulationRows:
    """What a simulation stores in its four child tables."""

    modes: tuple[ModeRow, ...]
    choices: tuple[ChoiceRow, ...]
    pairs: tuple[PairRow, ...]
    stations: tuple[StationRow, ...]


def simulation_rows(outputs: SimulationOutputs) -> SimulationRows:
    """The rows of a simulation's outputs, as the simulations store writes them."""
    return SimulationRows(
        tuple(ModeRow(str(mode), count) for mode, count in outputs.travellers_per_mode.items()),
        tuple(
            ChoiceRow(
                option.origin_hub,
                option.destination_hub,
                option.arc_id,
                option.mode,
                option.travellers,
                option.price_paid_chf,
                option.displaced,
            )
            for option in outputs.options
        ),
        tuple(
            PairRow(origin, destination, n) for origin, destination, n in outputs.unserved_per_pair
        ),
        tuple(
            StationRow(
                station.station_id,
                station.bikes,
                station.station_id in outputs.stations_empty,
                station.station_id in outputs.stations_full,
            )
            for station in outputs.stations_end
        ),
    )


@dataclass(frozen=True)
class Difference:
    table: str
    scheme: str | None
    key: str
    field: str
    stored: object
    rerun: object


@dataclass(frozen=True)
class TableComparison:
    table: str
    scheme: str | None
    compared: int
    differences: tuple[Difference, ...]

    @property
    def matches(self) -> bool:
        return not self.differences


@dataclass(frozen=True)
class SolveVerification:
    """The compared tables and the seconds each re-run took, labelled."""

    tables: tuple[TableComparison, ...]
    durations: tuple[tuple[str, float], ...] = ()

    @property
    def matches(self) -> bool:
        return all(table.matches for table in self.tables)


def _values(row: Any) -> dict[str, object]:
    if is_dataclass(row):
        return {item.name: getattr(row, item.name) for item in fields(row)}
    return dict(row._asdict())


def _compare(
    table: str,
    scheme: str | None,
    stored: Sequence[Any],
    rerun: Sequence[Any],
    key_fields: Sequence[str],
) -> TableComparison:
    def keyed(rows: Sequence[Any]) -> dict[tuple[object, ...], dict[str, object]]:
        found = {}
        for row in rows:
            values = _values(row)
            found[tuple(values[name] for name in key_fields)] = values
        return found

    before, after = keyed(stored), keyed(rerun)
    differences: list[Difference] = []
    for key in sorted(set(before) | set(after), key=lambda item: tuple(str(part) for part in item)):
        name = _key_name(key, key_fields)
        if key not in after:
            differences.append(Difference(table, scheme, name, "row", PRESENT, MISSING))
        elif key not in before:
            differences.append(Difference(table, scheme, name, "row", MISSING, PRESENT))
        else:
            for field_name, value in before[key].items():
                if value != after[key][field_name]:
                    differences.append(
                        Difference(table, scheme, name, field_name, value, after[key][field_name])
                    )
    return TableComparison(table, scheme, len(set(before) & set(after)), tuple(differences))


def _key_name(key: tuple[object, ...], key_fields: Sequence[str]) -> str:
    if "origin_hub" in key_fields:
        pair = f"{key[0]}>{key[1]}"
        return pair if len(key) == 2 else f"{pair} {key[2]}"
    return str(key[0])


def compare_solve_rows(stored: Sequence[SolveRow], rerun: Sequence[SolveRow]) -> TableComparison:
    return _compare("solve_rows", None, stored, rerun, ("origin_hub", "destination_hub", "arc_id"))


def compare_simulation_rows(
    scheme: str, stored: SimulationRows, rerun: SimulationRows
) -> tuple[TableComparison, ...]:
    return (
        _compare("simulation_modes", scheme, stored.modes, rerun.modes, ("mode",)),
        _compare(
            "simulation_choices",
            scheme,
            stored.choices,
            rerun.choices,
            ("origin_hub", "destination_hub", "arc_id"),
        ),
        _compare(
            "simulation_pairs",
            scheme,
            stored.pairs,
            rerun.pairs,
            ("origin_hub", "destination_hub"),
        ),
        _compare("simulation_stations", scheme, stored.stations, rerun.stations, ("station_id",)),
    )


def _difference_line(item: Difference) -> str:
    scheme = f" {item.scheme}" if item.scheme else ""
    return (
        f"{item.table}{scheme} [{item.key}] {item.field}: stored {item.stored}, re-run {item.rerun}"
    )


def _table_line(item: TableComparison) -> str:
    scheme = f" {item.scheme}" if item.scheme else ""
    count = f"{item.compared} row{'' if item.compared == 1 else 's'} compared"
    return f"{item.table}{scheme}: {count}, {'match' if item.matches else 'differ'}"


def report_lines(solve_id: str, verification: SolveVerification) -> tuple[str, ...]:
    """One line per difference, one per compared table, one per duration, then the verdict."""
    verdict = "match" if verification.matches else "differ"
    return (
        *(_difference_line(item) for table in verification.tables for item in table.differences),
        *(_table_line(table) for table in verification.tables),
        *(f"{label}: {seconds:.2f} s" for label, seconds in verification.durations),
        f"verify {solve_id}: {verdict}",
    )
