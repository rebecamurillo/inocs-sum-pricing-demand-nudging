from pathlib import Path

from pricing_demo.application.errors import (
    GtfsCopyChanged,
    NoCityDataYet,
    OtherTimetableInGraphFolder,
    UnknownCityDataset,
)
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_source_files import DatasetFiles
from pricing_demo.application.ports.trip_planner_graph import GraphBuilder, GraphFolder
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.trip_planner_graph import GraphManifest, ServiceWindow


class BuildTripPlannerGraph:
    """Build OpenTripPlanner's graph from a data set's timetable, with its service window."""

    def __init__(
        self,
        datasets: CityDatasets,
        files: DatasetFiles,
        folder: GraphFolder,
        builder: GraphBuilder,
    ) -> None:
        self._datasets = datasets
        self._files = files
        self._folder = folder
        self._builder = builder

    def execute(self, dataset_id: str | None) -> Path:
        dataset = self._pick(dataset_id)
        others = self._folder.other_gtfs_zips()
        if others:
            raise OtherTimetableInGraphFolder(others)
        osm = self._folder.osm_file()
        source = self._files.resolve(dataset.gtfs.file)
        if self._sha256_or_none(source) != dataset.gtfs.sha256:
            raise GtfsCopyChanged(
                f"The timetable copy of {dataset.id} ({source}) is missing or no longer "
                "matches its hash."
            )
        # Everything is checked: from here on the folder changes. A manifest never describes a
        # graph that was not built from it, so the old one goes before the build.
        self._folder.remove_manifest()
        gtfs = self._folder.put_gtfs(source)
        config = ServiceWindow.of(dataset.gtfs).build_config()
        self._folder.write_build_config(config)
        self._builder.build()
        return self._folder.write_manifest(
            GraphManifest(
                otp_image=self._builder.image,
                dataset_id=dataset.id,
                gtfs_sha256=self._folder.sha256(gtfs),
                osm_file=osm.name,
                osm_sha256=self._folder.sha256(osm),
                build_config=config,
            )
        )

    def _sha256_or_none(self, path: Path) -> str | None:
        try:
            return self._files.sha256(path)
        except OSError:
            return None

    def _pick(self, dataset_id: str | None) -> CityDataset:
        if dataset_id is None:
            latest = self._datasets.latest()
            if latest is None:
                raise NoCityDataYet
            return latest
        for dataset in self._datasets.list():
            if dataset.id == dataset_id:
                return dataset
        raise UnknownCityDataset(dataset_id)
