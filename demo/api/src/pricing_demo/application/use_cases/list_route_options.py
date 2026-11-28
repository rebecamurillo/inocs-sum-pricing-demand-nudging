from dataclasses import dataclass

from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.trip_reads import TripReads
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.option_prices import option_travel_time_s
from pricing_demo.domain.read_model import RouteMode
from pricing_demo.domain.trip_quotes import (
    LINE_KINDS,
    HubPairNotFound,
    LineKindName,
    UnknownPeriodKey,
    leg_geometry,
    leg_line_string,
    transfers,
)


@dataclass(frozen=True)
class RouteOptionLeg:
    mode: str
    line: str | None
    from_name: str | None
    to_name: str | None
    duration_s: Number
    line_kind: LineKindName
    geometry: dict[str, object] | None


@dataclass(frozen=True)
class RouteOptionView:
    arc_id: str
    mode: RouteMode
    duration_s: Number
    transfers: Number
    bike_legs: Number
    legs: tuple[RouteOptionLeg, ...]


@dataclass(frozen=True)
class RouteOptions:
    items: tuple[RouteOptionView, ...]
    bus_shapes: bool


class ListRouteOptions:
    """The stored options of one hub pair with their legs and geometry, for drawing a route."""

    def __init__(self, instances: CityInstances, trips: TripReads) -> None:
        self._instances = instances
        self._trips = trips

    def execute(
        self,
        instance_version_id: str,
        period_key: str | None,
        origin_hub: str,
        destination_hub: str,
    ) -> RouteOptions:
        if self._instances.get_version(instance_version_id) is None:
            raise InstanceVersionNotFound(instance_version_id)
        if period_key is not None and period_key not in {
            period.key for period in self._instances.periods_of(instance_version_id)
        }:
            raise UnknownPeriodKey(instance_version_id, period_key)
        area = self._trips.area(instance_version_id)
        if area is None or (origin_hub, destination_hub) not in area.hub_pairs:
            raise HubPairNotFound(origin_hub, destination_hub)
        options = self._trips.pair_options(instance_version_id, origin_hub, destination_hub)
        return RouteOptions(
            tuple(
                RouteOptionView(
                    option.arc_id,
                    option.mode,
                    Number(
                        option_travel_time_s(
                            option.mode,
                            option.total_travel_time_s,
                            option.total_transfer_time_s,
                            option.parking_time_min,
                        ),
                        "seconds",
                        "trip_planner",
                        "headline",
                    ),
                    Number(transfers(option.legs), "transfers", "derived", "headline"),
                    Number(option.bike_legs or 0, "bike_legs", "input", "headline"),
                    tuple(
                        RouteOptionLeg(
                            leg.mode,
                            leg.line,
                            leg.from_place,
                            leg.to_place,
                            Number(leg.duration_s, "seconds", "trip_planner", "headline"),
                            LINE_KINDS[leg.line_kind],
                            leg_line_string(leg_geometry(option.geometry, index)),
                        )
                        for index, leg in enumerate(option.legs)
                    ),
                )
                for option in options
            ),
            area.bus_shapes,
        )
