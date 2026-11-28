"""Place names a traveller can type: the stops and bike stations of an instance that belong to a
hub, a parent station and its platforms counted as one line."""

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pricing_demo.domain.read_model import StationRow

MIN_QUERY_LENGTH = 2
MAX_LINES = 10
PlaceKind = Literal["stop", "bike_station"]
_KINDS: Mapping[str, PlaceKind] = {"pt": "stop", "bs": "bike_station"}


@dataclass(frozen=True)
class PlaceLine:
    name: str
    kind: PlaceKind
    hub_id: str
    lat: float
    lon: float


def normalise(text: str) -> str:
    """Without case and accents: `Gare Cornavin` and `gare cornavín` are the same text."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def place_lines(
    q: str, stations: Sequence[StationRow], station_hubs: Mapping[str, str]
) -> list[PlaceLine]:
    """The lines whose name contains `q`; names that start with it first, then alphabetical.
    A line takes the position of its station with the lowest id."""
    wanted = normalise(q.strip())
    if len(wanted) < MIN_QUERY_LENGTH:
        return []
    grouped: dict[tuple[str, PlaceKind, str], StationRow] = {}
    for station in sorted(stations, key=lambda s: s.station_id):
        hub_id = station_hubs.get(station.station_id)
        if hub_id is None or wanted not in normalise(station.name):
            continue
        grouped.setdefault((station.name, _KINDS[station.kind], hub_id), station)
    lines = [
        PlaceLine(name, kind, hub_id, station.lat, station.lon)
        for (name, kind, hub_id), station in grouped.items()
    ]
    lines.sort(
        key=lambda line: (
            not normalise(line.name).startswith(wanted),
            normalise(line.name),
            line.name,
            line.kind,
            line.hub_id,
        )
    )
    return lines[:MAX_LINES]
