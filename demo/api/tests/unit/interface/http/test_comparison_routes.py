from dataclasses import replace
from typing import Any

from tests.unit.interface.http.conftest import ResultsApp
from tests.unit.interface.http.test_pricing_result_routes import NUMBER_KEYS, SOURCES, numbers_in

GOALS = [
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "pt_fare_chf",
    "car_parking_fee_chf",
    "max_displayed_options",
    "flat_price_per_ride_chf",
]


def compare(app: ResultsApp, *ids: str, query: str = "") -> Any:
    return app.client.get(
        "/api/v1/comparisons",
        params={"pricing_versions": ",".join(ids)} | ({"period": query} if query else {}),
    )


def test_two_versions_answer_200_with_the_top_level_facts_and_every_number_sourced(
    results_app: ResultsApp,
) -> None:
    a = results_app.results.finished()
    b = results_app.results.finished(cost_bike_chf=0.7)

    response = compare(results_app, b, a)

    assert response.status_code == 200
    body = response.json()
    assert body["instance_version"] == {"id": "geneva-3km.v1", "name": "Geneva 3 km v1"}
    assert body["period"]["id"] == "geneva-3km.v1.mon-08"
    assert body["period"]["name"]
    assert [item["letter"] for item in body["versions"]] == ["A", "B"]
    first = body["versions"][0]
    assert first["id"] == a
    assert first["name"]
    assert list(first["goals"]) == GOALS
    assert {item["source"] for item in first["goals"].values()} == {"input"}
    assert first["goals"]["pt_fare_chf"]["unit"] == "chf"
    assert first["goals"]["max_displayed_options"]["unit"] == "none"
    assert [item["price_scheme"] for item in first["simulations"]] == ["model_prices", "flat"]
    assert first["simulations"][0]["rule_current"] is False
    assert first["package"]["fingerprint"]
    assert [item["name"] for item in body["groups"]] == [
        "simulated",
        "model",
        "derived",
        "goals_that_differ",
        "solver",
    ]
    found = numbers_in(body)
    assert len(found) > 100
    assert all(set(item) == NUMBER_KEYS for item in found)
    assert {item["source"] for item in found} <= SOURCES
    assert {item["group"] for item in found} <= {"headline", "advanced"}
    assert body["pair_differences"]["a"] == "A"
    assert body["pair_differences"]["b"] == "B"
    assert body["identical_solves"] == []
    assert len(body["flat_references"]) == 1
    row = body["groups"][0]["rows"][0]
    assert set(row) == {"key", "values", "changes", "flats", "best"}


def test_four_versions_answer_200_in_letter_order(results_app: ResultsApp) -> None:
    ids = [results_app.results.finished(cost_bike_chf=0.5 + 0.1 * index) for index in range(4)]

    response = compare(results_app, *reversed(ids))

    assert response.status_code == 200
    assert [item["letter"] for item in response.json()["versions"]] == ["A", "B", "C", "D"]


def test_an_unknown_version_answers_404(results_app: ResultsApp) -> None:
    a = results_app.results.finished()

    response = compare(results_app, a, "geneva-3km.v1.Z")

    assert response.status_code == 404
    assert response.json()["code"] == "pricing_version_not_found"


def test_versions_of_two_instance_versions_answer_409_different_instances(
    results_app: ResultsApp,
) -> None:
    a = results_app.results.finished()
    draft = results_app.results.version()
    pricing = results_app.results.rig.pricing
    stored = pricing.get(draft)
    assert stored is not None
    pricing._versions[draft] = replace(stored, instance_version_id="geneva-3km.v2")

    response = compare(results_app, a, draft)

    assert response.status_code == 409
    assert response.json()["code"] == "different_instances"


def test_a_version_without_a_result_answers_409_no_result(results_app: ResultsApp) -> None:
    a = results_app.results.finished()
    draft = results_app.results.version()

    response = compare(results_app, a, draft)

    assert response.status_code == 409
    assert response.json()["code"] == "no_result"


def test_one_or_five_versions_answer_422(results_app: ResultsApp) -> None:
    ids = [results_app.results.finished() for _ in range(5)]

    for chosen in (ids[:1], ids):
        response = compare(results_app, *chosen)
        assert response.status_code == 422
        assert response.json()["code"] == "version_count_out_of_range"


def test_the_contract_documents_the_route_with_200_404_409_and_422(
    results_app: ResultsApp,
) -> None:
    schema = results_app.client.app.openapi()  # type: ignore[attr-defined]

    operation = schema["paths"]["/api/v1/comparisons"]["get"]

    assert {"200", "404", "409", "422"} <= set(operation["responses"])
