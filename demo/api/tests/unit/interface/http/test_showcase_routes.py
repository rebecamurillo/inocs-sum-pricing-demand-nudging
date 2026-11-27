from tests.unit.interface.http.conftest import ResultsApp

SHOWCASE = "/api/v1/showcase"


def test_without_a_mark_the_showcase_answers_404_no_showcase(results_app: ResultsApp) -> None:
    response = results_app.client.get(SHOWCASE)

    assert response.status_code == 404
    assert response.json()["code"] == "no_showcase"


def test_a_finished_version_is_marked_and_read_back_with_its_headline_numbers(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    put = results_app.client.put(SHOWCASE, json={"pricing_version_id": version})
    get = results_app.client.get(SHOWCASE)

    assert put.status_code == 200
    assert get.status_code == 200
    assert put.json() == get.json()
    body = get.json()
    assert body["pricing_version_id"] == version
    assert body["period_id"] == "geneva-3km.v1.mon-08"
    assert body["letter"] == "A"
    assert body["instance_version_name"] == "Geneva 3 km v1"
    assert body["headline"]["ridership"]["source"] == "model"
    assert {item["group"] for item in body["headline"].values()} == {"headline"}
    result = results_app.client.get(f"/api/v1/pricing-versions/{version}/result").json()
    assert body["headline"] == result["headline"]


def test_a_new_mark_replaces_the_old_one(results_app: ResultsApp) -> None:
    first = results_app.results.finished()
    second = results_app.results.finished(flat_price_per_ride_chf=2.5)
    results_app.client.put(SHOWCASE, json={"pricing_version_id": first})

    results_app.client.put(SHOWCASE, json={"pricing_version_id": second})

    assert results_app.client.get(SHOWCASE).json()["pricing_version_id"] == second


def test_a_version_without_a_result_answers_409_no_result(results_app: ResultsApp) -> None:
    draft = results_app.results.version()

    response = results_app.client.put(SHOWCASE, json={"pricing_version_id": draft})

    assert response.status_code == 409
    assert response.json()["code"] == "no_result"


def test_a_period_the_version_does_not_price_answers_409_no_result(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    response = results_app.client.put(
        SHOWCASE, json={"pricing_version_id": version, "period_id": "other"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "no_result"


def test_an_unknown_version_answers_404(results_app: ResultsApp) -> None:
    response = results_app.client.put(SHOWCASE, json={"pricing_version_id": "geneva-3km.v1.Z"})

    assert response.status_code == 404
    assert response.json()["code"] == "pricing_version_not_found"


def test_a_request_without_a_version_answers_422(results_app: ResultsApp) -> None:
    assert results_app.client.put(SHOWCASE, json={}).status_code == 422


def test_deleting_the_showcased_version_answers_409_is_showcase_and_another_204(
    results_app: ResultsApp,
) -> None:
    first = results_app.results.finished()
    second = results_app.results.finished(flat_price_per_ride_chf=2.5)
    results_app.client.put(SHOWCASE, json={"pricing_version_id": first})

    refused = results_app.client.delete(f"/api/v1/pricing-versions/{first}")
    allowed = results_app.client.delete(f"/api/v1/pricing-versions/{second}")

    assert refused.status_code == 409
    assert refused.json()["code"] == "is_showcase"
    assert allowed.status_code == 204
    assert results_app.client.get(f"/api/v1/pricing-versions/{first}").status_code == 200
