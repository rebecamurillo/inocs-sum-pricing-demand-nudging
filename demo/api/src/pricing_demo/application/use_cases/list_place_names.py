from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.trip_reads import TripReads
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.place_names import PlaceLine, place_lines


class ListPlaceNames:
    """The stop and bike-station names of an instance version that match what a traveller
    typed, from the stored build; none until the version is built."""

    def __init__(self, instances: CityInstances, trips: TripReads) -> None:
        self._instances = instances
        self._trips = trips

    def execute(self, instance_version_id: str, q: str) -> list[PlaceLine]:
        if self._instances.get_version(instance_version_id) is None:
            raise InstanceVersionNotFound(instance_version_id)
        area = self._trips.area(instance_version_id)
        if area is None:
            return []
        return place_lines(q, area.stations, area.station_hubs)
