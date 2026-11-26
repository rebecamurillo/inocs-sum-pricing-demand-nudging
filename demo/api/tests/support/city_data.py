"""Inputs of the city data tests: a synthetic GTFS zip and a tiny OSM extract."""

import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parents[1] / "fixtures" / "city_data"
GTFS_FILES = FIXTURES / "gtfs"
TINY_PBF = FIXTURES / "tiny.osm.pbf"
# The bounding box of the header of tiny.osm.pbf is lon 6.05-6.30, lat 46.10-46.30; the stops
# of the synthetic feed span lon 6.10-6.20, lat 46.15-46.25. tiny.osm.pbf was written once
# with osmium.SimpleWriter: a Header with that box added, then two nodes.


def zip_gtfs(target: Path, *, without: tuple[str, ...] = ()) -> Path:
    """Zip the synthetic feed into `target`, leaving out the named files."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as archive:
        for path in sorted(GTFS_FILES.glob("*.txt")):
            if path.name not in without:
                archive.write(path, path.name)
    return target


def osm_folder(folder: Path, names: tuple[str, ...] = ("geneva.osm.pbf",)) -> Path:
    """A folder holding a copy of the tiny extract under each name."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(TINY_PBF.read_bytes())
    return folder
