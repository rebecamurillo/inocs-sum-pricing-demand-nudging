"""Points of the fake city, for the trip quotes: metres east and north of its centre (the
position of hub H1), and the failures and parameters that make every quote status reachable."""

import math
from collections.abc import Sequence

from pricing_demo.infrastructure.fakes.city_preparation import (
    HUB_METRES,
    METRES_PER_DEGREE_LATITUDE,
    hub_positions,
)

# The default minimum trip distance (500 m) ties the grouping distance, so the rig takes 600 m:
# H1 to H2 (300 m) and H2 to H4 (570 m) are under it, H5 to H1 (707 m) is not.
MINIMUM_TRIP_DISTANCE = ("min_od_distance_m", 600.0)
INSTANCE_CHANGES: Sequence[tuple[str, float]] = (MINIMUM_TRIP_DISTANCE,)
# H1 to H6 has no public-transport route; H4 to H1 has no car route.
ROUTE_FAILURES = (
    {
        "origin_hub": "H1",
        "destination_hub": "H6",
        "query": "pt_bike",
        "kind": "no_route",
        "message": "no public transport",
    },
    {
        "origin_hub": "H4",
        "destination_hub": "H1",
        "query": "car",
        "kind": "no_route",
        "message": "no car route",
    },
)


def at(east: float, north: float) -> str:
    """`lat,lon` of the point `east` and `north` metres from the centre of the city."""
    lat, lon = hub_positions()["H1"]
    return (
        f"{lat + north / METRES_PER_DEGREE_LATITUDE:.6f},"
        f"{lon + east / (METRES_PER_DEGREE_LATITUDE * math.cos(math.radians(lat))):.6f}"
    )


def near(hub: str, east: float = 20.0, north: float = 0.0) -> str:
    """A point a few metres from the hub's centre, inside its outline."""
    hub_east, hub_north = HUB_METRES[hub]
    return at(hub_east + east, hub_north + north)
