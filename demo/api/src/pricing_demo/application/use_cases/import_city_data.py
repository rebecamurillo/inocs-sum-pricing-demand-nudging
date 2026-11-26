from datetime import date
from pathlib import Path

from pricing_demo.application.ports.bike_station_feed import BikeStationFeed
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_source_files import (
    DatasetFiles,
    StreetExtract,
    TimetableReader,
)
from pricing_demo.application.ports.clock import Clock
from pricing_demo.domain.city_datasets import (
    GENEVA_NAME,
    GENEVA_PRESET,
    GENEVA_ROUTING_MOMENT,
    GENEVA_SLUG,
    CityDataset,
    GbfsSnapshot,
    GtfsSnapshot,
    dataset_id_for,
)


def claim_dataset_id(datasets: CityDatasets, files: DatasetFiles, day: date) -> str:
    """The first free id of the day whose folder this run creates.

    The folder is the claim: a run that finds it taken (another run on the same day, or a
    killed run's leftover) moves to the next suffix, so a failed run removes only its own.
    """
    taken = set(datasets.ids_starting_with(f"{GENEVA_SLUG}-{day.isoformat()}"))
    while True:
        dataset_id = dataset_id_for(GENEVA_SLUG, day, taken)
        if files.claim(dataset_id):
            return dataset_id
        taken.add(dataset_id)


class ImportCityData:
    """Import the timetable and a first bike-station snapshot as one immutable data set."""

    def __init__(
        self,
        datasets: CityDatasets,
        timetable: TimetableReader,
        streets: StreetExtract,
        files: DatasetFiles,
        feed: BikeStationFeed,
        clock: Clock,
    ) -> None:
        self._datasets = datasets
        self._timetable = timetable
        self._streets = streets
        self._files = files
        self._feed = feed
        self._clock = clock

    def execute(self, gtfs: Path, osm_dir: Path) -> CityDataset:
        # Everything that can refuse runs before anything is written.
        street_box = self._streets.bounds(osm_dir)
        facts = self._timetable.read(gtfs)
        area = facts.stops_bbox.intersection(street_box)
        now = self._clock.now()
        dataset_id = claim_dataset_id(self._datasets, self._files, now.date())
        try:
            gtfs_file = self._files.copy_in(dataset_id, gtfs)
            gtfs_sha256 = self._files.sha256(self._files.resolve(str(gtfs_file)))
            fetched = self._feed.fetch(self._files.folder(dataset_id))
            dataset = CityDataset(
                id=dataset_id,
                name=GENEVA_NAME,
                gtfs=GtfsSnapshot(
                    file=str(gtfs_file),
                    sha256=gtfs_sha256,
                    source_sha256=self._files.sha256(gtfs),
                    valid_from=facts.valid_from,
                    valid_to=facts.valid_to,
                    timezone=facts.timezone,
                ),
                gbfs=GbfsSnapshot(
                    file=self._files.relative(fetched.file),
                    sha256=self._files.sha256(fetched.file),
                    source_url=fetched.source_url,
                    fetched_at=self._clock.now(),
                ),
                available_area=area,
                preset=GENEVA_PRESET,
                routing_moment=GENEVA_ROUTING_MOMENT,
                created_at=now,
            )
            self._datasets.add(dataset)
        except BaseException:
            self._files.remove(dataset_id)
            raise
        return dataset
