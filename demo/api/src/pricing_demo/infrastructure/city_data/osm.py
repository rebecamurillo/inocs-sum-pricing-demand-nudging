from pathlib import Path

import osmium

from pricing_demo.application.errors import InvalidStreetExtract, StreetExtractNotFound
from pricing_demo.domain.city_datasets import BoundingBox


class PbfStreetExtract:
    """The bounding box in the header of the one `.osm.pbf` in a folder."""

    def file(self, osm_dir: Path) -> Path:
        found = sorted(path.name for path in osm_dir.glob("*.osm.pbf")) if osm_dir.is_dir() else []
        if len(found) != 1:
            raise StreetExtractNotFound(found)
        return osm_dir / found[0]

    def bounds(self, osm_dir: Path) -> BoundingBox:
        path = self.file(osm_dir)
        with osmium.io.Reader(str(path), osmium.osm.osm_entity_bits.NOTHING) as reader:
            box = reader.header().box()
        if not box.valid():
            raise InvalidStreetExtract(f"The header of {path.name} has no bounding box.")
        return BoundingBox(
            min_lon=box.bottom_left.lon,
            min_lat=box.bottom_left.lat,
            max_lon=box.top_right.lon,
            max_lat=box.top_right.lat,
        )
