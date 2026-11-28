"""Child process of `PackageBikeStationFeed`: fetch the station information with the package.

Usage: `python -m pricing_demo.infrastructure.pricing_model.fetch_bike_stations <target_dir>`.
Prints one JSON line `{"file": ..., "source_url": ...}`.
"""

import json
import sys
from pathlib import Path

from sum_nsm_dynamic_pricing.stations.providers.donkey import DonkeyRepublicProvider


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: fetch_bike_stations <target_dir>", file=sys.stderr)
        return 2
    target_dir = Path(argv[0])
    target_dir.mkdir(parents=True, exist_ok=True)
    file = DonkeyRepublicProvider().fetch_station_information(target_dir)
    print(json.dumps({"file": str(file), "source_url": DonkeyRepublicProvider.MANIFEST_URL}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
