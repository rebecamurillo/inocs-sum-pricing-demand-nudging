import json
import subprocess
import sys
from pathlib import Path

from pricing_demo.application.errors import BikeStationFetchFailed
from pricing_demo.application.ports.bike_station_feed import FetchedStations

TIMEOUT_S = 120


class PackageBikeStationFeed:
    """Fetches the Donkey Republic station information with the pricing package, in a child
    process: the package is used unmodified and never loaded into the worker."""

    def fetch(self, target_dir: Path) -> FetchedStations:
        command = [
            sys.executable,
            "-m",
            "pricing_demo.infrastructure.pricing_model.fetch_bike_stations",
            str(target_dir),
        ]
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, timeout=TIMEOUT_S, check=False
            )
        except subprocess.TimeoutExpired:
            raise BikeStationFetchFailed(
                f"The bike-station feed did not answer within {TIMEOUT_S} s."
            ) from None
        if done.returncode != 0:
            lines = [line for line in done.stderr.strip().splitlines() if line.strip()]
            reason = lines[-1] if lines else f"exit code {done.returncode}"
            raise BikeStationFetchFailed(f"The bike-station feed failed: {reason}")
        try:
            answer = json.loads(done.stdout.strip().splitlines()[-1])
            return FetchedStations(file=Path(answer["file"]), source_url=answer["source_url"])
        except (IndexError, KeyError, ValueError) as error:
            raise BikeStationFetchFailed(
                "The bike-station feed answered in an unexpected form."
            ) from error
