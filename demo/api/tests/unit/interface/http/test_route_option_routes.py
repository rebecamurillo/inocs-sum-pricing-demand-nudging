from typing import Any

from tests.unit.interface.http.conftest import ResultsApp
from tests.unit.interface.http.test_pricing_result_routes import NUMBER_KEYS, SOURCES, numbers_in

URL = "/api/v1/route-options"


def get(app: ResultsApp, **params: str) -> Any:
    return app.client.get(
        URL,
        params={
            "instance_version": "geneva-3km.v1",
            "origin_hub": "H1",
            "destination_hub": "H3",
            **params,
        },
    )


def test_a_pair_answers_its_options_with_line_kinds_and_line_string_geometry(
    results_app: ResultsApp,
) -> None:
    response = get(results_app)

    assert response.status_code == 200
    body = response.json()
    assert body["bus_shapes"] is True
    assert sorted(item["mode"] for item in body["items"]) == ["car", "pt_bike", "pt_only"]
    legs = [leg for item in body["items"] for leg in item["legs"]]
    assert {leg["line_kind"] for leg in legs} <= {"street_path", "timetable_shape", "straight_line"}
    assert {"street_path", "timetable_shape"} <= {leg["line_kind"] for leg in legs}
    geometry = legs[0]["geometry"]
    assert geometry["type"] == "LineString"
    lon, lat = geometry["coordinates"][0]
    assert 6.0 < lon < 6.3
    assert 46.0 < lat < 46.4


def test_every_number_of_the_options_has_value_unit_source_and_group(
    results_app: ResultsApp,
) -> None:
    found = numbers_in(get(results_app).json())

    assert found
    assert all(set(item) == NUMBER_KEYS for item in found)
    assert {item["source"] for item in found} <= SOURCES


def test_the_period_key_of_the_version_is_accepted(results_app: ResultsApp) -> None:
    assert get(results_app, period="mon-08").status_code == 200


def test_a_period_key_the_version_does_not_have_is_422(results_app: ResultsApp) -> None:
    response = get(results_app, period="tue-17")

    assert response.status_code == 422
    assert response.json()["code"] == "unknown_period"


def test_an_unknown_instance_version_is_404(results_app: ResultsApp) -> None:
    response = get(results_app, instance_version="nope.v1")

    assert response.status_code == 404
    assert response.json()["code"] == "instance_version_not_found"


def test_a_pair_that_is_not_in_the_instance_is_404(results_app: ResultsApp) -> None:
    response = get(results_app, origin_hub="H3", destination_hub="H4")

    assert response.status_code == 404
    assert response.json()["code"] == "hub_pair_not_found"


def test_a_missing_hub_is_a_validation_problem(results_app: ResultsApp) -> None:
    response = results_app.client.get(URL, params={"instance_version": "geneva-3km.v1"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
