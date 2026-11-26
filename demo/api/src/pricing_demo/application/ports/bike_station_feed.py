from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class FetchedStations:
    file: Path
    source_url: str


class BikeStationFeed(Protocol):
    def fetch(self, target_dir: Path) -> FetchedStations:
        """Fetch the station information once into `target_dir`.

        Raises BikeStationFetchFailed with the reason.
        """
        ...
