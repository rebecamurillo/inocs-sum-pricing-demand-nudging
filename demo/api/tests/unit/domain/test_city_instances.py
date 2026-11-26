from dataclasses import replace
from datetime import time

import pytest

from pricing_demo.domain.city_instances import (
    InstanceParameters,
    InvalidInstanceName,
    ParameterChange,
    first_period,
    instance_slug,
    parameters_from_defaults,
    version_id,
    what_changes,
)
from pricing_demo.domain.package_fingerprint import instance_defaults
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.runs import T0


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Geneva 3 km", "geneva-3km"),
        ("Geneva 3km", "geneva-3km"),
        ("Genève  centre", "geneve-centre"),
        ("  Lyon / Part-Dieu!  ", "lyon-part-dieu"),
        ("Zürich 12 Km 2", "zurich-12km-2"),
        ("a_b", "a-b"),
        ("Ville 2 bis", "ville-2bis"),
    ],
)
def test_the_slug_of_a_name(name: str, slug: str) -> None:
    assert instance_slug(name) == slug


@pytest.mark.parametrize("name", ["", "   ", "!!!", "—"])
def test_a_name_without_letters_or_digits_has_no_slug(name: str) -> None:
    with pytest.raises(InvalidInstanceName):
        instance_slug(name)


def test_the_id_of_a_version() -> None:
    assert version_id("geneva-3km", 1) == "geneva-3km.v1"
    assert version_id("geneva-3km", 12) == "geneva-3km.v12"


def test_the_first_period_comes_from_the_data_set() -> None:
    dataset = fake_city_dataset("geneva-2026-11-26", T0)

    period = first_period("geneva-3km.v1", dataset)

    assert period.id == "geneva-3km.v1.mon-08"
    assert period.instance_version_id == "geneva-3km.v1"
    assert (period.key, period.label) == ("mon-08", "Monday 08:00–09:00")  # noqa: RUF001
    assert (period.weekday, period.start_time, period.end_time) == (0, time(8), time(9))
    assert period.routing_date == dataset.routing_moment.date
    assert period.routing_time == dataset.routing_moment.time
    assert period.arrive_by is dataset.routing_moment.arrive_by
    assert period.routing_date_provisional is dataset.routing_moment.provisional


def test_the_package_defaults_become_parameters_with_the_preset_and_a_seed_of_42() -> None:
    dataset = fake_city_dataset("d", T0)

    parameters = parameters_from_defaults(FAKE_FINGERPRINT.defaults, dataset.preset)

    assert parameters == InstanceParameters(
        center_lat=dataset.preset.centre_lat,
        center_lon=dataset.preset.centre_lon,
        radius_m=dataset.preset.radius_m,
        clustering_threshold_m=500.0,
        clustering_buffer_m=100.0,
        min_od_distance_m=500.0,
        seed=42,
        fixed_capacity=20,
        min_demand=10,
        max_demand=70,
        min_inventory_pct=0.0,
        max_inventory_pct=1.0,
        min_park_time_min=1.0,
        max_park_time_min=5.0,
    )


def test_a_seed_the_package_defines_is_kept() -> None:
    dataset = fake_city_dataset("d", T0)
    defaults = {
        **FAKE_FINGERPRINT.defaults,
        "PipelineConfig": {**FAKE_FINGERPRINT.defaults["PipelineConfig"], "seed": 7},
    }

    assert parameters_from_defaults(defaults, dataset.preset).seed == 7


def test_the_package_names_map_to_the_columns() -> None:
    mapped = instance_defaults(FAKE_FINGERPRINT.defaults)

    assert mapped["min_park_time_min"] == 1.0
    assert mapped["max_park_time_min"] == 5.0
    assert mapped["fixed_capacity"] == 20
    assert mapped["clustering_threshold_m"] == 500.0
    assert "min_park_time" not in mapped
    assert "otp_url" not in mapped


def parameters() -> InstanceParameters:
    return parameters_from_defaults(FAKE_FINGERPRINT.defaults, fake_city_dataset("d", T0).preset)


def test_nothing_changes_against_itself() -> None:
    assert what_changes(parameters(), parameters()) == []


def test_what_changes_lists_each_differing_parameter_in_column_order() -> None:
    before = parameters()
    after = replace(before, seed=1.5, radius_m=4000, center_lat=46.0)

    assert what_changes(before, after) == [
        ParameterChange("center_lat", before.center_lat, 46.0),
        ParameterChange("radius_m", before.radius_m, 4000),
        ParameterChange("seed", 42, 1.5),
    ]


def test_a_whole_float_equals_the_same_integer() -> None:
    before = parameters()

    assert what_changes(before, replace(before, fixed_capacity=20.0)) == []
