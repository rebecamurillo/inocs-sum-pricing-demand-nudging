from typing import Any

import pytest

from tests.unit.interface.http.conftest import ResultsApp

NUMBER_KEYS = {"value", "unit", "source", "group"}
SOURCES = {"model", "package_summary", "input", "trip_planner", "derived", "simulation"}


def path(version: str, name: str) -> str:
    return f"/api/v1/pricing-versions/{version}/{name}"


def numbers_in(node: Any) -> list[dict[str, Any]]:
    """Every object of the body that is a number: it has a value, a unit, a source and a group."""
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if set(node) == NUMBER_KEYS:
            found.append(node)
        else:
            for item in node.values():
                found.extend(numbers_in(item))
    elif isinstance(node, list):
        for item in node:
            found.extend(numbers_in(item))
    return found


def test_the_result_answers_200_with_every_number_carrying_its_source_and_group(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    response = results_app.client.get(path(version, "result"))

    assert response.status_code == 200
    body = response.json()
    found = numbers_in(body)
    assert len(found) > 40
    assert {item["source"] for item in found} <= SOURCES
    assert {item["group"] for item in found} <= {"headline", "advanced"}
    assert all(isinstance(item["value"], int | float) for item in found)
    assert body["pricing_version_id"] == version
    assert body["period_id"] == "geneva-3km.v1.mon-08"


def test_the_result_has_the_headline_goals_simulations_split_and_option_count(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    body = results_app.client.get(path(version, "result")).json()

    assert body["headline"]["ridership"]["source"] == "model"
    assert body["headline"]["profit"]["source"] == "derived"
    assert [goal["name"] for goal in body["goals"]][:2] == ["ridership", "revenue"]
    assert body["goals"][0]["model_prices"]["source"] == "simulation"
    assert body["goals"][0]["flat"]["source"] == "simulation"
    assert [item["price_scheme"] for item in body["simulations"]] == ["model_prices", "flat"]
    first = body["simulations"][0]
    assert (first["rule_id"], first["rule_version"]) == ("balanced-score", 1)
    assert first["rule_parameters"] == {"price_weight": 0.5, "time_weight": 0.5}
    assert first["rule_current"] is False
    assert set(first["travellers"]) == {"pt_bike", "pt_only", "car"}
    assert {"displaced", "unserved", "bike_rides", "revenue", "cost"} <= set(first)
    assert len(body["simulation_history"]) == 2
    assert body["model_split"]["modal_split_pt_only"]["source"] == "model"
    assert body["hub_pairs_with_bike_option"]["source"] == "model"
    assert body["hub_pairs_with_bike_option"]["value"] > 0


def test_the_quality_and_the_package_summary_are_in_the_advanced_group_only(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    body = results_app.client.get(path(version, "result")).json()

    advanced = body["advanced"]
    assert advanced["solver_status_name"] == "OPTIMAL"
    for name in ("objective_value", "gap_pct", "solution_time_s", "solution_count"):
        assert advanced["numbers"][name]["group"] == "advanced"
        assert name not in body["headline"]
    assert advanced["numbers"]["package_avg_bike_price_offered"]["source"] == "package_summary"
    outside = {key: value for key, value in body.items() if key != "advanced"}
    for item in numbers_in(outside):
        assert item["source"] != "package_summary"
        if item["group"] == "advanced":
            assert item["source"] in {"input"}  # the coefficients, nothing of the solve


def test_the_provenance_and_the_coefficients_are_returned(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    body = results_app.client.get(path(version, "result")).json()

    provenance = body["provenance"]
    assert provenance["licence_kind"] == "full"
    assert provenance["package_commit"] == "0" * 40
    assert provenance["routing_date_provisional"] is True
    assert set(provenance["input_keys"]) == {"area", "hubs", "routes", "travellers_and_bikes"}
    # The rule and the date of each scheme's latest simulation (intent AC 2).
    by_scheme = {item["price_scheme"]: item for item in body["simulations"]}
    assert [item["price_scheme"] for item in provenance["simulations"]] == ["model_prices", "flat"]
    for item in provenance["simulations"]:
        latest = by_scheme[item["price_scheme"]]
        assert (item["rule_id"], item["rule_version"], item["created_at"]) == (
            latest["rule_id"],
            latest["rule_version"],
            latest["created_at"],
        )
    assert body["coefficients"]["ASC_PT"]["value"] == -0.756
    assert body["coefficients"]["ASC_PT"]["source"] == "input"


def test_the_absent_numbers_are_null_and_never_zero(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    body = results_app.client.get(path(version, "result")).json()

    mean = next(goal for goal in body["goals"] if goal["name"] == "mean_bike_price")
    assert mean["model_prices"] is None
    assert mean["flat"] is None
    assert mean["change"] is None


def test_the_hub_pair_results_list_each_pair_with_its_prices_and_options(
    results_app: ResultsApp,
) -> None:
    version = results_app.results.finished()

    response = results_app.client.get(path(version, "hub-pair-results"))

    assert response.status_code == 200
    items = response.json()["items"]
    assert items
    order = [(item["origin_hub"], item["destination_hub"]) for item in items]
    assert order == sorted(order)
    priced = [item for item in items if item["mean_bike_price"] is not None]
    unpriced = [item for item in items if item["mean_bike_price"] is None]
    assert priced
    assert unpriced
    for item in unpriced:
        assert item["min_bike_price"] is None
        assert item["max_bike_price"] is None
    first = priced[0]
    assert first["mean_bike_price"]["source"] == "derived"
    assert first["travellers"]["pt_bike"]["source"] == "model"
    option = next(o for o in first["options"] if o["bike_price"] is not None)
    assert option["bike_price"]["source"] == "model"
    assert option["riders"]["source"] == "model"
    assert option["duration"]["source"] == "trip_planner"
    assert option["bike_legs"]["source"] == "input"
    assert {"mode", "duration_s", "distance_m", "line_kind"} <= set(option["legs"][0])
    assert all(item["source"] in SOURCES for item in numbers_in(items))
    legs = [leg for item in items for o in item["options"] for leg in o["legs"]]
    assert all({"line", "from_place", "to_place"} <= set(leg) for leg in legs)
    assert any(leg["line"] and leg["to_place"] for leg in legs)


def test_the_hub_results_list_each_hub_with_its_centre_and_rides(results_app: ResultsApp) -> None:
    version = results_app.results.finished()

    response = results_app.client.get(path(version, "hub-results"))

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["hub_id"] for item in items] == sorted(item["hub_id"] for item in items)
    assert {"lat", "lon", "label"} <= set(items[0])
    assert items[0]["rides_starting"]["source"] == "derived"
    assert any(item["mean_bike_price"] is None for item in items)


@pytest.mark.parametrize("name", ["result", "hub-pair-results", "hub-results"])
def test_an_unknown_version_answers_404_pricing_version_not_found(
    results_app: ResultsApp, name: str
) -> None:
    response = results_app.client.get(path("geneva-3km.v1.Z", name))

    assert response.status_code == 404
    assert response.json()["code"] == "pricing_version_not_found"


@pytest.mark.parametrize("name", ["result", "hub-pair-results", "hub-results"])
def test_a_draft_answers_404_no_result(results_app: ResultsApp, name: str) -> None:
    version = results_app.results.version()

    response = results_app.client.get(path(version, name))

    assert response.status_code == 404
    assert response.json()["code"] == "no_result"


@pytest.mark.parametrize("name", ["result", "hub-pair-results", "hub-results"])
def test_a_period_the_version_does_not_price_answers_404_no_result(
    results_app: ResultsApp, name: str
) -> None:
    version = results_app.results.finished()

    response = results_app.client.get(path(version, name), params={"period": "other"})

    assert response.status_code == 404
    assert response.json()["code"] == "no_result"
