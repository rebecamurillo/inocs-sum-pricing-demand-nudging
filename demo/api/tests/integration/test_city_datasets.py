"""The PostgreSQL adapter's own behaviour; the shared suite is contract/test_city_datasets.py."""

from datetime import date

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pricing_demo.domain.city_datasets import GENEVA_PRESET
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.persistence.city_datasets import PostgresCityDatasets
from tests.support.runs import T0

pytestmark = pytest.mark.integration


def test_the_table_has_the_columns_of_the_data_set(migrated_database: Engine) -> None:
    with migrated_database.connect() as connection:
        columns = connection.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'city_datasets' ORDER BY ordinal_position"
            )
        ).all()

    assert [name for name, _ in columns] == [
        "id",
        "name",
        "gtfs_file",
        "gtfs_sha256",
        "gtfs_source_sha256",
        "gtfs_valid_from",
        "gtfs_valid_to",
        "gtfs_timezone",
        "gbfs_file",
        "gbfs_sha256",
        "gbfs_source_url",
        "gbfs_fetched_at",
        "available_area",
        "preset",
        "routing_date",
        "routing_time",
        "arrive_by",
        "routing_date_provisional",
        "created_at",
    ]
    assert {nullable for _, nullable in columns} == {"NO"}


def test_the_stored_json_holds_the_polygon_and_the_preset(migrated_database: Engine) -> None:
    PostgresCityDatasets(migrated_database).add(fake_city_dataset("a", T0))

    with migrated_database.connect() as connection:
        row = connection.execute(text("SELECT available_area, preset FROM city_datasets")).one()

    assert row.available_area["type"] == "Polygon"
    assert row.preset == {
        "centre_lat": GENEVA_PRESET.centre_lat,
        "centre_lon": GENEVA_PRESET.centre_lon,
        "radius_m": 3000,
    }


def test_a_validity_that_ends_before_it_starts_is_refused(migrated_database: Engine) -> None:
    from dataclasses import replace

    original = fake_city_dataset("a", T0)
    backwards = replace(original, gtfs=replace(original.gtfs, valid_from=date(2025, 12, 14)))

    with pytest.raises(IntegrityError):
        PostgresCityDatasets(migrated_database).add(backwards)
