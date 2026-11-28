from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.application.ports.trip_reads import TripArea
from pricing_demo.domain.read_model import RouteFailure, RouteOptionRow
from pricing_demo.domain.runs import STEP_NUMBERS, StepName

_NEEDED = (StepName.AREA, StepName.HUBS, StepName.ROUTES, StepName.TRAVELLERS_AND_BIKES)


class StoredTripReads:
    """`TripReads` over the stored ports (instances, artefacts, the read model, the failures
    of the routes step), so the PostgreSQL adapter and the fake answer by the same rule."""

    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        artifacts: Artifacts,
        read_model: ReadModel,
        route_failures: RouteFailures,
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._artifacts = artifacts
        self._read_model = read_model
        self._route_failures = route_failures

    def area(self, instance_version_id: str) -> TripArea | None:
        version = self._instances.get_version(instance_version_id)
        links = self._artifacts.links_of(instance_version_id)
        if version is None or any(step not in links for step in _NEEDED):
            return None
        instance = self._instances.get_instance(version.instance_id)
        dataset = None if instance is None else self._datasets.get(instance.dataset_id)
        if dataset is None:
            return None
        hubs = self._read_model.hubs(links[StepName.HUBS])
        parameters = version.parameters
        return TripArea(
            centre=(float(parameters.center_lat), float(parameters.center_lon)),
            radius_m=float(parameters.radius_m),
            min_od_distance_m=float(parameters.min_od_distance_m),
            period_ids={
                period.key: period.id for period in self._instances.periods_of(instance_version_id)
            },
            stations=self._read_model.stations(links[StepName.AREA]),
            hubs=hubs,
            station_hubs={
                station_id: hub.hub_id
                for hub in hubs
                for station_id in (*hub.pt_station_ids, *hub.bike_station_ids)
            },
            hub_pairs=frozenset(
                (pair.origin_hub, pair.destination_hub)
                for pair in self._read_model.hub_pairs(links[StepName.TRAVELLERS_AND_BIKES])
            ),
            bus_shapes=dataset.bus_shapes.status == "generated",
        )

    def pair_options(
        self, instance_version_id: str, origin_hub: str, destination_hub: str
    ) -> list[RouteOptionRow]:
        key = self._artifacts.links_of(instance_version_id).get(StepName.TRAVELLERS_AND_BIKES)
        if key is None:
            return []
        return self._read_model.route_options_of_pair(key, origin_hub, destination_hub)

    def pair_failures(
        self, instance_version_id: str, origin_hub: str, destination_hub: str
    ) -> list[RouteFailure]:
        # Not filtered by period: a kept artefact's failures carry the period of the version
        # whose run produced it, and one `routes` artefact holds one routing moment's failures.
        key = self._artifacts.links_of(instance_version_id).get(StepName.ROUTES)
        artifact = None if key is None else self._artifacts.get(key)
        if artifact is None or artifact.run_id is None:
            return []
        return [
            failure
            for failure in self._route_failures.of_step(
                artifact.run_id, STEP_NUMBERS[StepName.ROUTES]
            )
            if (failure.origin_hub, failure.destination_hub) == (origin_hub, destination_hub)
        ]
