from pathlib import Path

import pytest

from pricing_demo.application.errors import InvalidStreetExtract, StreetExtractNotFound
from pricing_demo.domain.city_datasets import BoundingBox
from pricing_demo.infrastructure.city_data.osm import PbfStreetExtract
from tests.support.city_data import osm_folder


def test_the_bounds_are_the_box_of_the_header(tmp_path: Path) -> None:
    folder = osm_folder(tmp_path / "osm")

    assert PbfStreetExtract().bounds(folder) == BoundingBox(6.05, 46.10, 6.30, 46.30)


def test_no_extract_is_an_error_that_says_none_was_found(tmp_path: Path) -> None:
    (tmp_path / "osm").mkdir()

    with pytest.raises(StreetExtractNotFound, match="none"):
        PbfStreetExtract().bounds(tmp_path / "osm")


def test_a_missing_folder_is_the_same_error(tmp_path: Path) -> None:
    with pytest.raises(StreetExtractNotFound) as error:
        PbfStreetExtract().bounds(tmp_path / "absent")

    assert error.value.found == []


def test_two_extracts_are_an_error_that_names_both(tmp_path: Path) -> None:
    folder = osm_folder(tmp_path / "osm", ("b.osm.pbf", "a.osm.pbf"))

    with pytest.raises(StreetExtractNotFound, match=r"a\.osm\.pbf, b\.osm\.pbf"):
        PbfStreetExtract().bounds(folder)


def test_other_files_are_ignored(tmp_path: Path) -> None:
    folder = osm_folder(tmp_path / "osm")
    (folder / "graph.obj").write_bytes(b"x")
    (folder / ".gitkeep").write_bytes(b"")

    assert PbfStreetExtract().bounds(folder).min_lon == 6.05


def test_a_header_without_a_box_is_refused(tmp_path: Path) -> None:
    import osmium

    folder = tmp_path / "osm"
    folder.mkdir()
    writer = osmium.SimpleWriter(str(folder / "nobox.osm.pbf"))
    writer.close()

    with pytest.raises(InvalidStreetExtract, match=r"nobox\.osm\.pbf"):
        PbfStreetExtract().bounds(folder)


def test_the_file_is_the_one_extract_of_the_folder(tmp_path: Path) -> None:
    folder = osm_folder(tmp_path / "osm", ("geneva.osm.pbf",))

    assert PbfStreetExtract().file(folder) == folder / "geneva.osm.pbf"


@pytest.mark.parametrize("names", [(), ("a.osm.pbf", "b.osm.pbf")])
def test_a_wrong_number_of_extracts_has_no_file(tmp_path: Path, names: tuple[str, ...]) -> None:
    folder = osm_folder(tmp_path / "osm", names)

    with pytest.raises(StreetExtractNotFound):
        PbfStreetExtract().file(folder)
