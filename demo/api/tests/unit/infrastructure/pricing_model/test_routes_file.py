from pricing_demo.infrastructure.pricing_model.routes_file import sorted_routes


def pair(origin: int, destination: int) -> dict[str, int]:
    return {"from_id": origin, "to_id": destination}


def test_the_pairs_are_ordered_by_origin_then_destination() -> None:
    payload = {"od_results": [pair(1, 0), pair(0, 2), pair(0, 1)]}

    result = sorted_routes(payload)

    assert result["od_results"] == [pair(0, 1), pair(0, 2), pair(1, 0)]


def test_other_keys_stay_and_the_input_is_unchanged() -> None:
    payload = {"generated_at": "t", "od_results": [pair(1, 0), pair(0, 1)]}

    result = sorted_routes(payload)

    assert result["generated_at"] == "t"
    assert payload["od_results"] == [pair(1, 0), pair(0, 1)]
