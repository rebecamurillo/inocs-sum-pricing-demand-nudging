import shutil
from pathlib import Path

from pricing_demo.application.ports.bike_station_feed import FetchedStations

FIXTURE = Path(__file__).parent / "fixtures" / "gbfs_station_information.json"
# The provider's manifest URL, as the real adapter reports it.
SOURCE_URL = "https://stables.donkey.bike/api/public/gbfs/2/donkey_ge/gbfs.json"


class FixtureBikeStationFeed:
    """Copies a committed GBFS `station_information` file; never reaches the network."""

    def __init__(self) -> None:
        self.fetches = 0

    def fetch(self, target_dir: Path) -> FetchedStations:
        self.fetches += 1
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "gbfs_station_information.json"
        shutil.copyfile(FIXTURE, target)
        return FetchedStations(file=target, source_url=SOURCE_URL)
