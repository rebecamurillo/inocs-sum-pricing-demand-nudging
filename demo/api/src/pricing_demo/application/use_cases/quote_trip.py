from dataclasses import dataclass

from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.solves import Solves
from pricing_demo.application.ports.trip_reads import TripArea, TripReads
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.domain.numbers import Number, NumberSource
from pricing_demo.domain.pricing_versions import PricingVersionNotFound, ResultNotFound
from pricing_demo.domain.read_model import RouteOptionRow
from pricing_demo.domain.trip_quotes import (
    NoPoint,
    PeriodNotPriced,
    Point,
    PointMatch,
    PointStatus,
    QuotedOption,
    QuoteStatus,
    has_car_option,
    haversine_m,
    match_point,
    offered_bike_options,
    parse_point,
    quote_status,
    quoted_options,
)


@dataclass(frozen=True)
class QuotedPoint:
    status: PointStatus
    hub_id: str | None
    hub_name: str | None
    nearest_stop_name: str | None
    distance_to_hub_centre_m: Number | None
    nearest_hub_id: str | None
    distance_from_outline_m: Number | None


@dataclass(frozen=True)
class QuotedHub:
    hub_id: str
    hub_name: str


@dataclass(frozen=True)
class TripQuote:
    status: QuoteStatus
    from_point: QuotedPoint | None
    to_point: QuotedPoint | None
    origin_hub: QuotedHub | None
    destination_hub: QuotedHub | None
    min_trip_distance_m: Number | None
    no_car_option: bool | None
    options: tuple[QuotedOption, ...]


def _metres(value: float, source: NumberSource) -> Number:
    return Number(value, "m", source, "headline")


def _quoted_point(match: PointMatch) -> QuotedPoint:
    return QuotedPoint(
        match.status,
        match.hub_id,
        match.hub_name,
        match.nearest_stop_name,
        None
        if match.distance_to_hub_centre_m is None
        else _metres(match.distance_to_hub_centre_m, "derived"),
        match.nearest_hub_id,
        None
        if match.distance_from_outline_m is None
        else _metres(match.distance_from_outline_m, "derived"),
    )


def _hub(match: PointMatch | None) -> QuotedHub | None:
    if match is None or match.hub_id is None or match.hub_name is None:
        return None
    return QuotedHub(match.hub_id, match.hub_name)


@dataclass(frozen=True)
class _Pair:
    hub_distance_m: float
    in_hub_pairs: bool
    pt_bike_failed: bool
    car_failed: bool
    options: list[RouteOptionRow]


class QuoteTrip:
    """Quotes a trip between two points from the stored build and result of a pricing version:
    PostgreSQL only, no trip planner, solver or worker (NFR-2)."""

    def __init__(
        self,
        lookup: ResultLookup,
        pricing: PricingVersions,
        solves: Solves,
        trips: TripReads,
    ) -> None:
        self._lookup = lookup
        self._pricing = pricing
        self._solves = solves
        self._trips = trips

    def execute(
        self,
        version_id: str,
        period_key: str | None,
        from_text: str | None,
        to_text: str | None,
    ) -> TripQuote:
        if from_text is None and to_text is None:
            raise NoPoint
        origin = None if from_text is None else parse_point(from_text)
        destination = None if to_text is None else parse_point(to_text)
        version = self._pricing.get(version_id)
        if version is None:
            raise PricingVersionNotFound(version_id)
        area = self._trips.area(version.instance_version_id)
        if area is None:
            raise ResultNotFound(version_id)
        found = self._lookup.find(version_id, self._period_id(version_id, area, period_key))
        origin_match = None if origin is None else self._match(origin, area)
        destination_match = None if destination is None else self._match(destination, area)
        options: tuple[QuotedOption, ...] = ()
        no_car_option: bool | None = None
        pair = None
        if (
            origin_match is not None
            and destination_match is not None
            and origin_match.status == destination_match.status == "matched"
            and origin_match.hub_id != destination_match.hub_id
        ):
            pair = self._pair(version.instance_version_id, area, origin_match, destination_match)
        rows = {row.arc_id: row for row in self._solves.rows(found.solve.key)} if pair else {}
        status = quote_status(
            origin_match,
            destination_match,
            None if pair is None else pair.hub_distance_m,
            area.min_od_distance_m,
            pair is not None and pair.in_hub_pairs,
            pair is not None and pair.pt_bike_failed,
            pair is not None and bool(offered_bike_options(pair.options, rows)),
        )
        if pair is not None and status in ("priced", "no_bike_option"):
            goals = found.version.goals
            options = quoted_options(
                pair.options, rows, float(goals.pt_fare_chf), float(goals.car_parking_fee_chf)
            )
            no_car_option = pair.car_failed or not has_car_option(pair.options)
        minimum = (
            _metres(area.min_od_distance_m, "input") if status == "under_minimum_distance" else None
        )
        return TripQuote(
            status,
            None if origin_match is None else _quoted_point(origin_match),
            None if destination_match is None else _quoted_point(destination_match),
            _hub(origin_match),
            _hub(destination_match),
            minimum,
            no_car_option,
            options,
        )

    def _pair(
        self,
        instance_version_id: str,
        area: TripArea,
        origin: PointMatch,
        destination: PointMatch,
    ) -> "_Pair":
        origin_hub, destination_hub = origin.hub_id or "", destination.hub_id or ""
        centres = {hub.hub_id: (hub.lat, hub.lon) for hub in area.hubs}
        failures = self._trips.pair_failures(instance_version_id, origin_hub, destination_hub)
        return _Pair(
            haversine_m(centres[origin_hub], centres[destination_hub]),
            (origin_hub, destination_hub) in area.hub_pairs,
            any(item.query == "pt_bike" for item in failures),
            any(item.query == "car" for item in failures),
            self._trips.pair_options(instance_version_id, origin_hub, destination_hub),
        )

    def _period_id(self, version_id: str, area: TripArea, period_key: str | None) -> str:
        priced = self._pricing.period_ids(version_id)
        if period_key is None:
            if not priced:
                raise ResultNotFound(version_id)
            return priced[0]
        period_id = area.period_ids.get(period_key)
        if period_id is None or period_id not in priced:
            raise PeriodNotPriced(version_id, period_key)
        return period_id

    @staticmethod
    def _match(point: Point, area: TripArea) -> PointMatch:
        return match_point(point, area.centre, area.radius_m, area.hubs, area.stations)
