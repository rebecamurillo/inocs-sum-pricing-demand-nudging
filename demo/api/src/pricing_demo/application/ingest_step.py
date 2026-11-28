"""Turns the files of a stored artefact into the read model's rows and the step's counts."""

from collections.abc import Mapping
from typing import Any

from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.application.ports.feed_shapes import FeedShapes
from pricing_demo.application.ports.read_model import IngestionBatch, ReadModel
from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.domain import read_model as rows
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.runs import STEP_NUMBERS, StepName


class StepIngestion:
    """Reads the artefact's files (and, for the last step, the routes artefact's), builds the
    rows and the counts with the domain's readers and hands them to the read model, which
    stores them in one transaction. A file that cannot be read or is malformed raises: the
    caller fails the step and the artefact stays."""

    def __init__(
        self,
        files: ArtifactFiles,
        read_model: ReadModel,
        route_failures: RouteFailures,
        feed_shapes: FeedShapes,
    ) -> None:
        self._files = files
        self._read_model = read_model
        self._route_failures = route_failures
        self._feed_shapes = feed_shapes

    def ingest(
        self, artifact: Artifact, dataset: CityDataset, upstream: Mapping[StepName, Artifact]
    ) -> Mapping[str, Any]:
        batch = self._batch(artifact, dataset, upstream)
        self._read_model.ingest(batch)
        return batch.counts

    def _read(self, artifact: Artifact, name: str) -> Any:
        return self._files.read_json(artifact.path, name)

    def _batch(
        self, artifact: Artifact, dataset: CityDataset, upstream: Mapping[StepName, Artifact]
    ) -> IngestionBatch:
        key, step = artifact.input_key, artifact.step
        if step is StepName.AREA:
            stations = rows.stations_from(self._read(artifact, "stations.json"))
            return IngestionBatch(key, step, rows.area_counts(stations), stations=stations)
        if step is StepName.HUBS:
            hubs = rows.hubs_from(
                self._read(artifact, "hubs.geojson"), self._read(artifact, "hub_polygons.geojson")
            )
            links = rows.station_hubs_from(self._read(artifact, "stations_hubs.geojson"))
            return IngestionBatch(key, step, rows.hubs_counts(hubs), hubs=hubs, station_hubs=links)
        if step is StepName.ROUTES:
            failures = (
                self._route_failures.of_step(artifact.run_id, STEP_NUMBERS[StepName.ROUTES])
                if artifact.run_id is not None
                else []
            )
            counts = rows.routes_counts(
                self._read(artifact, "od_routes.json"), artifact.reported_counts, failures
            )
            return IngestionBatch(
                key,
                step,
                counts,
                route_pairs=rows.route_pairs(self._read(artifact, "od_routes.json")),
            )
        instance = self._read(artifact, "Instance_1.json")
        routes = upstream[StepName.ROUTES]
        # An artefact stored before the bike legs were written has no such file: null.
        bike_legs = (
            self._read(artifact, "option_bike_legs.json")
            if any(item.name == "option_bike_legs.json" for item in artifact.files)
            else None
        )
        options = rows.route_options_from(
            self._read(routes, "od_routes.json"),
            self._read(routes, "od_geometry.json"),
            instance,
            self._feed_shapes.routes_with_shapes(dataset),
            bike_legs,
        )
        return IngestionBatch(
            key,
            step,
            rows.instance_counts(instance),
            hub_pairs=rows.hub_pairs_from(instance),
            route_options=options,
            station_bikes=rows.station_bikes_from(instance),
            deltas=rows.deltas_from(instance),
        )
