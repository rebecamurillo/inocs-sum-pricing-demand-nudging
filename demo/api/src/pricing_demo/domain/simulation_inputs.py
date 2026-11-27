"""The traveller simulation's instance, built from the stored read model."""

from collections.abc import Sequence

from pricing_demo.domain.read_model import (
    HubPairRow,
    OptionStationDeltaRow,
    RouteOptionRow,
    StationBikesRow,
)
from pricing_demo.domain.traveller_simulation import (
    SimulationInstance,
    SimulationOption,
    SimulationPair,
)


def simulation_instance_from(
    hub_pairs: Sequence[HubPairRow],
    route_options: Sequence[RouteOptionRow],
    station_bikes: Sequence[StationBikesRow],
    deltas: Sequence[OptionStationDeltaRow],
) -> SimulationInstance:
    """Demand becomes a whole number of travellers. A PT + bike option without its count of
    bike legs, or a car option without its cost and parking time (an artefact ingested before
    they were stored), cannot be priced: it raises `ValueError`."""
    options = []
    for row in route_options:
        if row.mode == "pt_bike" and row.bike_legs is None:
            raise ValueError(f"Option {row.arc_id} has no count of bike legs.")
        options.append(
            SimulationOption(
                row.arc_id,
                row.origin_hub,
                row.destination_hub,
                row.mode,
                row.total_travel_time_s,
                row.total_transfer_time_s,
                row.bike_legs or 0,
                row.car_cost_chf,
                row.parking_time_min,
            )
        )
    return SimulationInstance(
        tuple(
            SimulationPair(pair.origin_hub, pair.destination_hub, int(pair.demand))
            for pair in hub_pairs
        ),
        tuple(options),
        tuple(station_bikes),
        tuple(deltas),
    )
