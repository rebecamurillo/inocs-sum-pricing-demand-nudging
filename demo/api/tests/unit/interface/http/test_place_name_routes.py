from typing import Any

from tests.unit.interface.http.conftest import ResultsApp

URL = "/api/v1/place-names"


def get(app: ResultsApp, **params: str) -> Any:
    return app.client.get(URL, params={"instance_version": "geneva-3km.v1", **params})


def test_a_typed_name_answers_the_matching_lines_whatever_the_case(
    results_app: ResultsApp,
) -> None:
    response = get(results_app, q="FAKE stop h1")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["name"] for item in items] == [f"Fake stop H1-{n}" for n in range(1, 6)]
    assert all(set(item) == {"name", "kind", "hub_id", "lat", "lon"} for item in items)
    assert {(item["kind"], item["hub_id"]) for item in items} == {("stop", "H1")}


def test_a_bike_station_has_its_kind(results_app: ResultsApp) -> None:
    items = get(results_app, q="bikes h2").json()["items"]

    assert {item["kind"] for item in items} == {"bike_station"}


def test_at_most_ten_lines_come_back(results_app: ResultsApp) -> None:
    assert len(get(results_app, q="fake").json()["items"]) == 10


def test_a_short_text_answers_no_line(results_app: ResultsApp) -> None:
    response = get(results_app, q="f")

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_an_unknown_instance_version_is_404(results_app: ResultsApp) -> None:
    response = results_app.client.get(URL, params={"instance_version": "nope.v1", "q": "fake"})

    assert response.status_code == 404
    assert response.json()["code"] == "instance_version_not_found"


def test_a_missing_text_is_a_validation_problem(results_app: ResultsApp) -> None:
    response = results_app.client.get(URL, params={"instance_version": "geneva-3km.v1"})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_failed"
