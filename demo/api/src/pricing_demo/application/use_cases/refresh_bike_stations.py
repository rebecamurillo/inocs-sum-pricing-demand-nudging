from dataclasses import replace

from pricing_demo.application.errors import GtfsCopyChanged, NoCityDataYet
from pricing_demo.application.ports.bike_station_feed import BikeStationFeed
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_source_files import DatasetFiles
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.use_cases.import_city_data import claim_dataset_id
from pricing_demo.domain.city_datasets import CityDataset, GbfsSnapshot


class RefreshBikeStations:
    """A new data set: the latest one's timetable and a new bike-station snapshot."""

    def __init__(
        self, datasets: CityDatasets, files: DatasetFiles, feed: BikeStationFeed, clock: Clock
    ) -> None:
        self._datasets = datasets
        self._files = files
        self._feed = feed
        self._clock = clock

    def execute(self) -> CityDataset:
        latest = self._datasets.latest()
        if latest is None:
            raise NoCityDataYet
        now = self._clock.now()
        dataset_id = claim_dataset_id(self._datasets, self._files, now.date())
        try:
            gtfs_file = self._files.copy_in(dataset_id, self._files.resolve(latest.gtfs.file))
            if self._files.sha256(self._files.resolve(str(gtfs_file))) != latest.gtfs.sha256:
                raise GtfsCopyChanged(
                    f"The timetable copy of {latest.id} no longer matches its hash."
                )
            fetched = self._feed.fetch(self._files.folder(dataset_id))
            dataset = replace(
                latest,
                id=dataset_id,
                gtfs=replace(latest.gtfs, file=str(gtfs_file)),
                gbfs=GbfsSnapshot(
                    file=self._files.relative(fetched.file),
                    sha256=self._files.sha256(fetched.file),
                    source_url=fetched.source_url,
                    fetched_at=self._clock.now(),
                ),
                created_at=now,
            )
            self._datasets.add(dataset)
        except BaseException:
            self._files.remove(dataset_id)
            raise
        return dataset
