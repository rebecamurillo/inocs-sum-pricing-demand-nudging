from tests.unit.interface.http.conftest import Faked


def test_no_data_set_lists_an_empty_collection(faked_without_city_data: Faked) -> None:
    response = faked_without_city_data.client.get("/api/v1/city-datasets")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_a_data_set_is_listed_with_its_facts(faked: Faked) -> None:
    response = faked.client.get("/api/v1/city-datasets")

    assert response.status_code == 200
    (item,) = response.json()["items"]
    assert item == {
        "id": "geneva-2026-11-26",
        "name": "Geneva · tpg + Donkey Republic",
        "gtfs_valid_from": "2024-12-15",
        "gtfs_valid_to": "2025-12-13",
        "gtfs_timezone": "Europe/Zurich",
        "gbfs_fetched_at": "2026-11-10T00:00:00Z",
        "available_area": {
            "type": "Polygon",
            "coordinates": [
                [[6.05, 46.12], [6.25, 46.12], [6.25, 46.29], [6.05, 46.29], [6.05, 46.12]]
            ],
        },
        "preset": {
            "centre_lat": 46.20565363888243,
            "centre_lon": 6.148903476290692,
            "radius_m": 3000,
        },
        "routing_moment": {
            "date": "2025-03-10",
            "time": "08:30:00",
            "arrive_by": True,
            "provisional": True,
        },
        "bus_shapes": "generated",
        "bus_shapes_reason": None,
        "shape_tool_image": "fake-bus-shape-matcher",
    }


def test_a_data_set_without_shapes_lists_the_reason_and_the_tool() -> None:
    from dataclasses import replace

    from pricing_demo.domain.city_datasets import BusShapes
    from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
    from pricing_demo.interface.http.schemas import CityDatasetResource
    from tests.support.runs import T0

    dataset = replace(
        fake_city_dataset("a", T0), bus_shapes=BusShapes.none("Docker is not available", "img")
    )

    resource = CityDatasetResource.from_domain(dataset)

    assert (resource.bus_shapes, resource.bus_shapes_reason, resource.shape_tool_image) == (
        "none",
        "Docker is not available",
        "img",
    )
