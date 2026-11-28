import pytest

from pricing_demo.domain.build_plan import BUILD_STEPS, STEP_OUTPUTS
from pricing_demo.domain.build_verification import (
    BuildDescription,
    PairContent,
    compare_builds,
    instance_pair_contents,
    report_lines,
    route_pair_contents,
)
from pricing_demo.domain.runs import StepName

VERSION = "geneva-3km.v1"
AB, CD = ("A", "B"), ("C", "D")


def hashes(seed: str) -> dict[StepName, dict[str, str]]:
    return {step: {name: f"{seed}-{name}" for name in STEP_OUTPUTS[step]} for step in BUILD_STEPS}


def build(
    seed: str = "s",
    *,
    failed: frozenset[tuple[str, str]] = frozenset(),
    routes: dict[tuple[str, str], PairContent] | None = None,
    instance: dict[tuple[str, str], PairContent] | None = None,
) -> BuildDescription:
    return BuildDescription(
        hashes(seed),
        failed,
        routes if routes is not None else {AB: PairContent(("o1",)), CD: PairContent(("o2",))},
        instance
        if instance is not None
        else {AB: PairContent(("o1",), 3.0), CD: PairContent(("o2",), 4.0)},
    )


def test_two_builds_with_the_same_hashes_match() -> None:
    comparison = compare_builds(build(), build())

    assert comparison.matches
    lines = report_lines(VERSION, comparison)
    assert len(lines) == 5
    for line, step in zip(lines, BUILD_STEPS, strict=False):
        assert line.startswith(f"{step.value}: match")
        for name in STEP_OUTPUTS[step]:
            assert f"{name} stored s-{name} rebuilt s-{name}" in line
    assert lines[-1] == f"verify-build {VERSION}: match"


def test_one_file_that_differs_makes_its_step_and_the_verdict_differ() -> None:
    rebuilt = build()
    files = {step: dict(found) for step, found in rebuilt.files.items()}
    files[StepName.HUBS]["hubs.geojson"] = "other"
    comparison = compare_builds(
        build(),
        BuildDescription(files, rebuilt.failed_pairs, rebuilt.route_pairs, rebuilt.instance_pairs),
    )

    assert not comparison.matches
    lines = report_lines(VERSION, comparison)
    assert lines[0].startswith("area: match")
    assert lines[1].startswith("hubs: differ")
    assert "hubs.geojson stored s-hubs.geojson rebuilt other" in lines[1]
    assert "stations_hubs.geojson stored s-stations_hubs.geojson rebuilt s-" in lines[1]
    assert lines[-1] == f"verify-build {VERSION}: differ"


def test_a_pair_one_build_failed_is_reported_with_the_build_that_has_it_and_excluded() -> None:
    stored = build(failed=frozenset({CD}))
    # The other seed changes every file: steps 3 and 4 are decided by their pairs.
    rebuilt = build("t")
    files = {
        **rebuilt.files,
        **{step: stored.files[step] for step in (StepName.AREA, StepName.HUBS)},
    }
    rebuilt = BuildDescription(
        files, rebuilt.failed_pairs, rebuilt.route_pairs, rebuilt.instance_pairs
    )

    comparison = compare_builds(stored, rebuilt)

    assert comparison.matches
    lines = report_lines(VERSION, comparison)
    assert lines[2].startswith("routes: match")
    assert "1 pair compared" in lines[2]
    assert "C>D only in the rebuilt build" in lines[2]
    assert lines[3].startswith("travellers_and_bikes: match")
    assert "C>D only in the rebuilt build" in lines[3]
    assert lines[-1] == f"verify-build {VERSION}: match"


def test_a_pair_failed_in_the_rebuild_is_listed_with_the_stored_build() -> None:
    rebuilt = build(failed=frozenset({AB}))

    lines = report_lines(VERSION, compare_builds(build(), rebuilt))

    assert "A>B only in the stored build" in lines[2]


def test_a_compared_pair_with_another_demand_makes_step_four_differ() -> None:
    stored = build(failed=frozenset({CD}))
    rebuilt = build(
        failed=frozenset({CD}),
        instance={AB: PairContent(("o1",), 9.0), CD: PairContent(("o2",), 4.0)},
    )

    comparison = compare_builds(stored, rebuilt)

    assert not comparison.matches
    lines = report_lines(VERSION, comparison)
    assert lines[2].startswith("routes: match")
    assert lines[3].startswith("travellers_and_bikes: differ")
    assert "A>B differs" in lines[3]


def test_a_compared_pair_with_other_options_makes_step_three_differ() -> None:
    stored = build(failed=frozenset({CD}))
    rebuilt = build(
        failed=frozenset({CD}), routes={AB: PairContent(("other",)), CD: PairContent(("o2",))}
    )

    assert not compare_builds(stored, rebuilt).matches


def test_a_failure_in_the_stored_build_only_still_compares_by_pairs() -> None:
    stored = build(failed=frozenset({CD}))
    rebuilt = build("t")

    comparison = compare_builds(stored, rebuilt)

    # The files differ (other seed) but the pairs both builds have are equal.
    assert [step.matches for step in comparison.steps][2:] == [True, True]
    assert not comparison.matches  # steps 1 and 2 differ


def test_steps_one_and_two_always_compare_their_files_even_with_failures() -> None:
    comparison = compare_builds(build(failed=frozenset({AB})), build("t", failed=frozenset({AB})))

    assert [step.matches for step in comparison.steps[:2]] == [False, False]


def test_options_are_equal_when_only_their_ids_differ() -> None:
    def routes(arc_id: str) -> tuple[object, object]:
        arc = {"arc_id": arc_id, "total_travel_time_s": 10, "legs": []}
        return (
            {
                "od_results": [
                    {
                        "from_id": "A",
                        "to_id": "B",
                        "arc_pt_bike": [arc],
                        "arc_pt_only": [],
                        "arc_car": [],
                    }
                ]
            },
            {"geometries": [{"arc_id": arc_id, "legs_geometry": [{"leg_idx": 0}]}]},
        )

    assert route_pair_contents(*routes("1b")) == route_pair_contents(*routes("9b"))


def test_options_differ_when_their_geometry_differs() -> None:
    od = {
        "od_results": [
            {
                "from_id": "A",
                "to_id": "B",
                "arc_pt_bike": [],
                "arc_pt_only": [],
                "arc_car": [{"arc_id": "c", "total_travel_time_s": 1}],
            }
        ]
    }

    one = route_pair_contents(od, {"geometries": [{"arc_id": "c", "legs_geometry": [1]}]})
    two = route_pair_contents(od, {"geometries": [{"arc_id": "c", "legs_geometry": [2]}]})

    assert one != two
    assert set(one) == {AB}
    assert one[AB].demand is None
    assert "arc_id" not in one[AB].options[0]


def test_the_instance_reader_pairs_the_demand_with_the_arcs_of_the_pair() -> None:
    instance = {
        "OD_pairs": [{"origin": "A", "destination": "B", "demand": 5, "euclid_dist": 10}],
        "arcs_pt_bike": {"A_B": [{"arc_id": "1b", "t": 1}]},
        "arcs_pt_only": {},
        "car_paths": {"A_B": [{"arc_id": "c1", "t": 2}]},
    }

    found = instance_pair_contents(instance)

    assert set(found) == {AB}
    assert found[AB].demand == 5
    assert len(found[AB].options) == 2
    assert all("arc_id" not in option for option in found[AB].options)


@pytest.mark.parametrize("bad", [{}, {"od_results": [{"from_id": "A"}]}, None])
def test_a_malformed_routes_file_is_a_value_error(bad: object) -> None:
    with pytest.raises(ValueError, match="od_routes"):
        route_pair_contents(bad, {"geometries": []})


@pytest.mark.parametrize("bad", [{}, {"OD_pairs": [{"origin": "A"}]}, None])
def test_a_malformed_instance_is_a_value_error(bad: object) -> None:
    with pytest.raises(ValueError, match="Instance_1"):
        instance_pair_contents(bad)
