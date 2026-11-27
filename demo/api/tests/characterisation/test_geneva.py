"""Steps 1 and 2 on the committed Geneva timetable (read in place, never copied into the
repository), the committed bike-station snapshot and a 500 m radius at the preset centre.

The golden numbers were fixed at the first run (2026-11-27, package sources of commit f159853,
pandas 3.1.1; the committed snapshot has no station within 500 m of the centre). They change only
with a change of the package or of the feed, and the commit says why.
"""

import json
import threading
from pathlib import Path

import pytest

from pricing_demo.domain.runs import StepName
from tests.characterisation.rig import GBFS_FIXTURE, GENEVA_GTFS, make_city

pytestmark = pytest.mark.characterisation

GOLDEN = {"stops": 66, "bike_stations": 0, "hubs": 5}


def test_the_geneva_timetable_gives_the_golden_stop_station_and_hub_counts(tmp_path: Path) -> None:
    city = make_city(tmp_path / "data", GENEVA_GTFS, GBFS_FIXTURE, "geneva")
    folder = tmp_path / "w"
    never = threading.Event()

    area = city.prepare(folder, StepName.AREA, never, radius_m=500)
    hubs = city.prepare(folder, StepName.HUBS, never, radius_m=500)

    assert (area.failure_code, hubs.failure_code) == (None, None), (area, hubs)
    stations = json.loads((folder / "stations.json").read_text(encoding="utf-8"))["stations"]
    found = {
        "stops": sum(item["type"] == "pt" for item in stations),
        "bike_stations": sum(item["type"] == "bs" for item in stations),
        "hubs": len(json.loads((folder / "hubs.geojson").read_text(encoding="utf-8"))["features"]),
    }
    assert found == GOLDEN
