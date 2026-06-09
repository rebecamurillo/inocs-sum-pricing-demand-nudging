# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from pathlib import Path

import requests

from ...utils.io import write_json
from .base import GBFSProvider


class DonkeyRepublicProvider(GBFSProvider):
    MANIFEST_URL = "https://stables.donkey.bike/api/public/gbfs/2/donkey_ge/gbfs.json"

    def fetch_station_information(self, output_dir: Path) -> Path:
        manifest = requests.get(self.MANIFEST_URL, timeout=30).json()
        languages = manifest.get("data", {})
        first_lang = next(iter(languages.values()))
        feeds = first_lang.get("feeds", [])
        station_feed = next(feed for feed in feeds if feed["name"] == "station_information")
        station_info_url = station_feed["url"]
        station_info = requests.get(station_info_url, timeout=30).json()
        target = output_dir / "gbfs_station_information.json"
        write_json(target, station_info)
        return target
