from typing import Any

import pytest

from tests.support.trips import at, near
from tests.unit.interface.http.conftest import ResultsApp
from tests.unit.interface.http.test_pricing_result_routes import NUMBER_KEYS, SOURCES, numbers_in

URL = "/api/v1/trip-quotes"
# Each quote status, and the points that make it (the fake city, minimum trip distance 600 m).
CASES = {
    "one_point": (near("H1"), None),
    "outside_zone": (near("H1"), at(4000, 0)),
    "no_hub_here": (near("H1"), at(0, 1800)),
    "same_hub": (near("H1", 10), near("H1", -10)),
    "under_minimum_distance": (near("H1"), near("H2")),
    "no_route": (near("H1"), near("H6")),
    "removed_by_quality_check": (near("H3"), near("H4")),
    "no_bike_option": (near("H5"), near("H1")),
    "priced": (near("H1"), near("H3")),
}


def get(app: ResultsApp, version: str, origin: str | None, destination: str | None) -> Any:
    params = {"pricing_version": version}
    if origin is not None:
        params["from"] = origin
    if destination is not None:
        params["to"] = destination
    return app.client.get(URL, params=params)


@pytest.mark.parametrize("status", list(CASES))
def test_every_quote_status_answers_200_with_exactly_that_status(
    results_app: ResultsApp, status: str
) -> None:
    version = results_app.results.finished()

    response = get(results_app, version, *CASES[status])

    assert response.status_code == 200
    assert response.json()["status"] == status


def test_a_priced_quote_carries_the_hubs_points_and_options(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    body = get(results_app, version, *CASES["priced"]).json()

    assert body["origin_hub"]["hub_id"] == "H1"
    assert body["destination_hub"]["hub_id"] == "H3"
    assert body["origin_hub"]["hub_name"]
    assert body["from_point"]["status"] == "matched"
    assert body["from_point"]["nearest_stop_name"]
    assert body["from_point"]["distance_to_hub_centre_m"]["unit"] == "m"
    assert body["no_car_option"] is False
    assert [option["mode"] for option in body["options"]] == ["pt_bike", "pt_only", "car"]
    assert [option["most_taken"] for option in body["options"]] == [True, True, True]
    for option in body["options"]:
        assert {"price", "duration_s", "transfers", "legs", "flow", "bike_legs"} <= set(option)
        assert all(
            {"mode", "line", "from_name", "to_name", "duration_s"} == set(leg)
            for leg in option["legs"]
        )
    assert "geometry" not in str(body)


def test_every_number_of_a_quote_has_value_unit_source_and_group(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    body = get(results_app, version, *CASES["priced"]).json()

    found = numbers_in(body)
    assert len(found) > 20
    assert all(set(item) == NUMBER_KEYS for item in found)
    assert {item["source"] for item in found} <= SOURCES
    assert {item["group"] for item in found} == {"headline"}
    prices = [option["price"] for option in body["options"]]
    assert {item["source"] for item in prices} == {"derived"}


def test_a_no_hub_here_quote_names_the_nearest_hub_and_the_distance(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    body = get(results_app, version, *CASES["no_hub_here"]).json()

    assert body["to_point"]["status"] == "no_hub_here"
    assert body["to_point"]["nearest_hub_id"] == "H6"
    assert body["to_point"]["distance_from_outline_m"]["value"] > 300


def test_an_under_minimum_distance_quote_carries_the_minimum(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    body = get(results_app, version, *CASES["under_minimum_distance"]).json()

    assert body["min_trip_distance_m"]["value"] == 600


def test_a_no_bike_option_quote_returns_pt_and_car_options_only(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    body = get(results_app, version, *CASES["no_bike_option"]).json()

    assert [option["mode"] for option in body["options"]] == ["pt_only", "car"]


def test_a_pair_with_a_car_route_failure_says_so(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    body = get(results_app, version, near("H4"), near("H1")).json()

    assert body["no_car_option"] is True


def test_the_period_key_of_the_version_is_accepted(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    response = results_app.client.get(
        URL, params={"pricing_version": version, "period": "mon-08", "from": near("H1")}
    )

    assert response.status_code == 200


def problem(response: Any, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code


def test_an_unknown_pricing_version_is_404(results_app: ResultsApp) -> None:
    problem(get(results_app, "geneva-3km.v1.Z", near("H1"), None), 404, "pricing_version_not_found")


def test_a_version_without_a_finished_result_is_404_no_result(results_app: ResultsApp) -> None:
    draft = results_app.results.version()

    problem(get(results_app, draft, near("H1"), None), 404, "no_result")


def test_a_period_the_version_did_not_price_is_422(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    response = results_app.client.get(
        URL, params={"pricing_version": version, "period": "tue-17", "from": near("H1")}
    )

    problem(response, 422, "period_not_priced")


def test_no_point_is_422(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    problem(get(results_app, version, None, None), 422, "no_point")


@pytest.mark.parametrize("text", ["abc", "46.2", "91,6"])
def test_a_malformed_coordinate_is_422(results_app: ResultsApp, text: str) -> None:
    version = results_app.results.finished()

    problem(get(results_app, version, text, None), 422, "malformed_point")


def test_a_missing_pricing_version_is_a_validation_problem(results_app: ResultsApp) -> None:
    response = results_app.client.get(URL, params={"from": near("H1")})

    problem(response, 422, "validation_failed")
