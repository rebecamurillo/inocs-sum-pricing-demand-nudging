from datetime import date, time

import pytest

from pricing_demo.domain.city_datasets import (
    GENEVA_NAME,
    GENEVA_PRESET,
    GENEVA_ROUTING_MOMENT,
    GENEVA_SLUG,
    NO_BUS_SHAPE_REASON,
    BoundingBox,
    BusShapes,
    DisjointAreas,
    city_data_status,
    city_name,
    dataset_id_for,
    is_bus_route_type,
)
from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.system_status import NO_CITY_DATA_REASON, ComponentName, ComponentState

DAY = date(2026, 11, 26)


def test_the_first_id_of_a_day_is_the_slug_and_the_date() -> None:
    assert dataset_id_for(GENEVA_SLUG, DAY, set()) == "geneva-2026-11-26"


def test_a_taken_id_gets_the_next_free_suffix() -> None:
    assert dataset_id_for("geneva", DAY, {"geneva-2026-11-26"}) == "geneva-2026-11-26-2"
    assert (
        dataset_id_for("geneva", DAY, {"geneva-2026-11-26", "geneva-2026-11-26-2"})
        == "geneva-2026-11-26-3"
    )


def test_a_gap_in_the_suffixes_is_not_filled_before_the_first_free_one() -> None:
    taken = {"geneva-2026-11-26", "geneva-2026-11-26-3"}

    assert dataset_id_for("geneva", DAY, taken) == "geneva-2026-11-26-2"


def test_another_day_starts_again() -> None:
    assert (
        dataset_id_for("geneva", date(2026, 11, 27), {"geneva-2026-11-26"}) == "geneva-2026-11-27"
    )


def test_overlapping_boxes_intersect() -> None:
    first = BoundingBox(6.0, 46.0, 6.3, 46.3)
    second = BoundingBox(6.1, 46.1, 6.5, 46.5)

    assert first.intersection(second) == BoundingBox(6.1, 46.1, 6.3, 46.3)


def test_a_contained_box_is_its_own_intersection() -> None:
    inner = BoundingBox(6.1, 46.1, 6.2, 46.2)

    assert BoundingBox(6.0, 46.0, 6.3, 46.3).intersection(inner) == inner
    assert inner.intersection(BoundingBox(6.0, 46.0, 6.3, 46.3)) == inner


def test_disjoint_boxes_have_no_intersection() -> None:
    with pytest.raises(DisjointAreas):
        BoundingBox(6.0, 46.0, 6.1, 46.1).intersection(BoundingBox(7.0, 47.0, 7.1, 47.1))


def test_the_disjoint_error_is_a_domain_error() -> None:
    assert issubclass(DisjointAreas, DomainError)


def test_the_polygon_is_a_closed_ring_in_longitude_latitude_order() -> None:
    polygon = BoundingBox(6.0, 46.0, 6.3, 46.5).to_geojson_polygon()

    assert polygon["type"] == "Polygon"
    ring = polygon["coordinates"][0]  # type: ignore[index]
    assert ring[0] == ring[-1] == [6.0, 46.0]
    assert ring == [[6.0, 46.0], [6.3, 46.0], [6.3, 46.5], [6.0, 46.5], [6.0, 46.0]]


def test_no_data_set_makes_city_data_unavailable_with_its_reason() -> None:
    status = city_data_status(0)

    assert status.name is ComponentName.CITY_DATA
    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason == NO_CITY_DATA_REASON


def test_a_data_set_makes_city_data_available() -> None:
    assert city_data_status(1).state is ComponentState.AVAILABLE
    assert city_data_status(3).reason is None


def test_the_geneva_constants() -> None:
    assert GENEVA_NAME == "Geneva · tpg + Donkey Republic"
    assert (GENEVA_PRESET.centre_lat, GENEVA_PRESET.centre_lon, GENEVA_PRESET.radius_m) == (
        46.20565363888243,
        6.148903476290692,
        3000,
    )
    assert GENEVA_ROUTING_MOMENT.date == date(2025, 3, 10)
    assert GENEVA_ROUTING_MOMENT.time == time(8, 30)
    assert GENEVA_ROUTING_MOMENT.arrive_by
    assert GENEVA_ROUTING_MOMENT.provisional


@pytest.mark.parametrize(
    ("route_type", "is_bus"),
    [
        (0, False),
        (1, False),
        (2, False),
        (3, True),
        (100, False),
        (199, False),
        (700, True),
        (799, True),
        (800, False),
        (900, False),
        (999, False),
    ],
)
def test_only_basic_and_extended_bus_route_types_are_bus(route_type: int, is_bus: bool) -> None:
    assert is_bus_route_type(route_type) is is_bus


def test_generated_bus_shapes_carry_the_tool_image_and_no_reason() -> None:
    shapes = BusShapes.generated("pfaedle@sha256:abc")

    assert (shapes.status, shapes.reason, shapes.tool_image) == (
        "generated",
        None,
        "pfaedle@sha256:abc",
    )


def test_bus_shapes_none_carry_the_reason_and_the_tool_image() -> None:
    shapes = BusShapes.none("Docker is not available", "pfaedle@sha256:abc")

    assert (shapes.status, shapes.reason, shapes.tool_image) == (
        "none",
        "Docker is not available",
        "pfaedle@sha256:abc",
    )


def test_bus_shapes_none_require_a_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        BusShapes.none("", "pfaedle@sha256:abc")


def test_the_reason_for_no_shape_is_the_quoted_sentence() -> None:
    assert NO_BUS_SHAPE_REASON == "no bus shape was produced"


def test_the_city_name_is_the_part_of_the_data_set_name_before_the_first_separator() -> None:
    assert city_name(GENEVA_NAME) == "Geneva"
    assert city_name("Zurich") == "Zurich"
