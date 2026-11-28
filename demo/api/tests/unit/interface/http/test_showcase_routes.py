import pytest

from tests.unit.interface.http.conftest import SERVER_TIME, CityInstancesApp, ResultsApp

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


@pytest.mark.parametrize("flag", ["", "?including_pricing_versions=true"])
def test_deleting_what_holds_the_showcase_answers_409_is_showcase(
    instances_app: CityInstancesApp, flag: str
) -> None:
    created = instances_app.client.post(
        "/api/v1/city-instances",
        json={
            "name": "Geneva 3 km",
            "dataset_id": "geneva-2026-11-26",
            "start_from": {"kind": "package_defaults"},
        },
    )
    assert created.status_code == 201
    instances_app.rig.showcase.mark("geneva-3km.v1.A", "geneva-3km.v1.mon-08", SERVER_TIME)

    for path in (
        f"/api/v1/instance-versions/geneva-3km.v1{flag}",
        f"/api/v1/city-instances/geneva-3km{flag}",
    ):
        response = instances_app.client.delete(path)
        assert response.status_code == 409, path
        assert response.json()["code"] == "is_showcase"

    assert instances_app.instances.get_version("geneva-3km.v1") is not None
    assert instances_app.rig.showcase.current() is not None


def test_the_showcase_answers_what_home_draws_with_every_number_sourced_and_grouped(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished(flat_price_per_ride_chf=1.0)
    results_app.client.put(SHOWCASE, json={"pricing_version_id": version})

    body = results_app.client.get(SHOWCASE).json()

    assert body["scope"]["city"] == "Geneva"
    assert body["scope"]["period_label"] == "Monday 08:00\u201309:00"
    assert body["scope"]["radius_km"]["value"] == 3
    assert body["scope"]["radius_km"]["source"] == "input"
    assert body["flat_price"] == {
        "value": 1.0,
        "unit": "chf_per_ride",
        "source": "input",
        "group": "headline",
    }
    for name in ("car_share_flat", "car_share_version", "car_share_difference"):
        assert set(body[name]) == {"value", "unit", "source", "group"}
        assert (body[name]["source"], body[name]["group"]) == ("simulation", "headline")
    assert body["car_share_difference"]["value"] == pytest.approx(
        body["car_share_flat"]["value"] - body["car_share_version"]["value"]
    )
    assert set(body["rule"]) == {"id", "version", "rule_current"}
    assert body["rule"]["rule_current"] is False
    assert body["study_circle"]["radius_m"]["value"] == 3000
    assert body["study_circle"]["centre"]["lat"]["source"] == "input"
    assert body["hubs"]
    assert {"id", "centre", "outline"} == set(body["hubs"][0])
    assert body["hub_pairs"]
    for pair in body["hub_pairs"]:
        assert (pair["mean_bike_price"]["source"], pair["bike_rides"]["source"]) == (
            "derived",
            "derived",
        )
        assert pair["bike_rides"]["value"] > 0
        assert pair["origin"]["lat"]["group"] == "headline"
