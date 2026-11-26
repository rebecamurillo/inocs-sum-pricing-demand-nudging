"""City data sets: an immutable import of a city's timetable and bike stations."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, time

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.system_status import ComponentName, ComponentStatus, no_city_data_status

GENEVA_SLUG = "geneva"
GENEVA_NAME = "Geneva · tpg + Donkey Republic"


class DisjointAreas(DomainError):
    pass


@dataclass(frozen=True)
class BoundingBox:
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def intersection(self, other: "BoundingBox") -> "BoundingBox":
        box = BoundingBox(
            max(self.min_lon, other.min_lon),
            max(self.min_lat, other.min_lat),
            min(self.max_lon, other.max_lon),
            min(self.max_lat, other.max_lat),
        )
        if box.min_lon >= box.max_lon or box.min_lat >= box.max_lat:
            raise DisjointAreas("The timetable's stops and the street extract do not overlap.")
        return box

    def to_geojson_polygon(self) -> dict[str, object]:
        """A closed ring, longitude first, counter-clockwise."""
        ring = [
            [self.min_lon, self.min_lat],
            [self.max_lon, self.min_lat],
            [self.max_lon, self.max_lat],
            [self.min_lon, self.max_lat],
            [self.min_lon, self.min_lat],
        ]
        return {"type": "Polygon", "coordinates": [ring]}


@dataclass(frozen=True)
class Preset:
    centre_lat: float
    centre_lon: float
    radius_m: int


@dataclass(frozen=True)
class RoutingMoment:
    date: date
    time: time
    arrive_by: bool
    provisional: bool


@dataclass(frozen=True)
class GtfsSnapshot:
    file: str
    sha256: str
    source_sha256: str
    valid_from: date
    valid_to: date
    timezone: str


@dataclass(frozen=True)
class GbfsSnapshot:
    file: str
    sha256: str
    source_url: str
    fetched_at: datetime


@dataclass(frozen=True)
class CityDataset:
    id: str
    name: str
    gtfs: GtfsSnapshot
    gbfs: GbfsSnapshot
    available_area: BoundingBox
    preset: Preset
    routing_moment: RoutingMoment
    created_at: datetime


GENEVA_PRESET = Preset(centre_lat=46.20565363888243, centre_lon=6.148903476290692, radius_m=3000)
# Provisional until the author answers follow-up Q-29.
GENEVA_ROUTING_MOMENT = RoutingMoment(
    date=date(2025, 3, 10), time=time(8, 30), arrive_by=True, provisional=True
)


def dataset_id_for(slug: str, import_date: date, taken: Collection[str]) -> str:
    """`geneva-2026-11-26`, then `-2`, `-3`, ... when the id is taken."""
    base = f"{slug}-{import_date.isoformat()}"
    if base not in taken:
        return base
    suffix = 2
    while f"{base}-{suffix}" in taken:
        suffix += 1
    return f"{base}-{suffix}"


def city_data_status(count: int) -> ComponentStatus:
    if count > 0:
        return ComponentStatus.ready(ComponentName.CITY_DATA)
    return no_city_data_status()
