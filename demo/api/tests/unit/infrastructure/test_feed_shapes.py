import zipfile
from dataclasses import replace
from pathlib import Path

from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.infrastructure.city_data.feed_shapes import GtfsFeedShapes
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.feed_shapes import FakeFeedShapes
from tests.support.city_data import GTFS_FILES, zip_gtfs
from tests.support.runs import T0


def dataset_with(file: str) -> CityDataset:
    dataset = fake_city_dataset("geneva-2026-11-26", T0)
    return replace(dataset, gtfs=replace(dataset.gtfs, file=file))


def test_a_feed_without_shapes_gives_the_empty_set(tmp_path: Path) -> None:
    zip_gtfs(tmp_path / "datasets" / "d" / "gtfs.zip")

    found = GtfsFeedShapes(tmp_path).routes_with_shapes(dataset_with("datasets/d/gtfs.zip"))

    assert found == frozenset()


def test_the_routes_with_a_shaped_trip_are_found_by_their_public_code(tmp_path: Path) -> None:
    target = tmp_path / "datasets" / "d" / "gtfs.zip"
    target.parent.mkdir(parents=True)
    with zipfile.ZipFile(target, "w") as archive:
        for path in sorted(GTFS_FILES.glob("*.txt")):
            if path.name != "trips.txt":
                archive.write(path, path.name)
        archive.writestr(
            "trips.txt", "route_id,service_id,trip_id,shape_id\nR1,WD,T1,S1\nR2,WD,T2,\n"
        )

    found = GtfsFeedShapes(tmp_path).routes_with_shapes(dataset_with("datasets/d/gtfs.zip"))

    assert found == frozenset({"1"})


def test_the_answer_is_read_once_per_data_set(tmp_path: Path) -> None:
    target = zip_gtfs(tmp_path / "datasets" / "d" / "gtfs.zip")
    shapes = GtfsFeedShapes(tmp_path)
    dataset = dataset_with("datasets/d/gtfs.zip")
    shapes.routes_with_shapes(dataset)

    target.unlink()

    assert shapes.routes_with_shapes(dataset) == frozenset()


def test_the_fake_answers_the_same_codes_for_every_data_set() -> None:
    dataset = fake_city_dataset("geneva-2026-11-26", T0)

    assert FakeFeedShapes({"1"}).routes_with_shapes(dataset) == frozenset({"1"})
