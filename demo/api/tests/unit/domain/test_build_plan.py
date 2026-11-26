from collections.abc import Collection, Mapping
from dataclasses import replace
from datetime import time
from typing import Any

from pricing_demo.domain.build_plan import (
    BUILD_STEPS,
    STEP_PARAMETERS,
    BuildPlan,
    Cause,
    canonical_inputs,
    causes_between,
    graph_manifest_sha256,
    input_key,
    plan_build,
    step_inputs,
)
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import (
    InstanceParameters,
    first_period,
    parameters_from_defaults,
)
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from tests.support.runs import T0

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)
PERIOD = first_period("geneva-3km.v1", DATASET)
FINGERPRINT = "a" * 64
MANIFEST = {"otp_image": "otp:2.10", "gtfs_sha256": "0" * 64, "dataset_id": "geneva"}
NO_DURATIONS: dict[StepName, float | None] = {}


Inputs = dict[StepName, dict[str, Any] | None]


def inputs_of(**changes: Any) -> Inputs:
    return step_inputs(replace(PARAMETERS, **changes), DATASET, PERIOD, FINGERPRINT, MANIFEST)


def keys_of(inputs: Inputs) -> dict[StepName, str | None]:
    return {step: input_key(value) if value else None for step, value in inputs.items()}


def plan(
    parameters: InstanceParameters = PARAMETERS,
    *,
    dataset: CityDataset = DATASET,
    fingerprint: str | None = FINGERPRINT,
    manifest: Mapping[str, object] | None = MANIFEST,
    stored: Collection[str] = (),
    based_on: Mapping[StepName, Mapping[str, Any]] | None = None,
    durations: Mapping[StepName, float | None] = NO_DURATIONS,
) -> BuildPlan:
    return plan_build(
        parameters, dataset, PERIOD, fingerprint, manifest, set(stored), based_on, durations
    )


def test_a_key_is_the_sha256_of_the_canonical_json_whatever_the_order_of_the_keys() -> None:
    assert input_key({"b": 1, "a": [1, 2]}) == input_key({"a": [1, 2], "b": 1})
    assert len(input_key({"a": 1})) == 64
    assert input_key({"a": 1}) != input_key({"a": 2})


def test_the_keys_are_stable_between_two_computations() -> None:
    assert keys_of(inputs_of()) == keys_of(inputs_of())


def test_a_whole_number_hashes_the_same_as_the_same_number_with_a_decimal() -> None:
    once = inputs_of(radius_m=3000)
    again = inputs_of(radius_m=3000.0)

    assert keys_of(once) == keys_of(again)


def test_each_step_reads_only_its_own_parameters() -> None:
    first = keys_of(inputs_of())

    changed = keys_of(inputs_of(min_od_distance_m=900.0))

    assert changed[StepName.AREA] == first[StepName.AREA]
    assert changed[StepName.HUBS] == first[StepName.HUBS]
    assert changed[StepName.ROUTES] != first[StepName.ROUTES]
    assert changed[StepName.TRAVELLERS_AND_BIKES] != first[StepName.TRAVELLERS_AND_BIKES]


def test_a_changed_upstream_key_changes_every_downstream_key() -> None:
    first = keys_of(inputs_of())

    changed = keys_of(inputs_of(radius_m=2000.0))

    assert all(changed[step] != first[step] for step in BUILD_STEPS)


def test_the_travellers_step_alone_changes_when_only_its_parameters_change() -> None:
    first = keys_of(inputs_of())

    changed = keys_of(inputs_of(seed=7))

    assert [changed[s] == first[s] for s in BUILD_STEPS] == [True, True, True, False]


def test_every_parameter_is_read_by_one_step_and_the_number_of_workers_by_none() -> None:
    names = [name for step in BUILD_STEPS for name in STEP_PARAMETERS[step]]

    assert len(names) == len(set(names)) == 14
    assert not any("otp_workers" in str(value) for value in inputs_of().values())


def test_the_routing_moment_is_in_the_keys_of_steps_three_and_four_only() -> None:
    first = keys_of(inputs_of())
    moved = step_inputs(
        PARAMETERS, DATASET, replace(PERIOD, routing_time=time(9, 0)), FINGERPRINT, MANIFEST
    )

    changed = keys_of(moved)

    assert [changed[s] == first[s] for s in BUILD_STEPS] == [True, True, False, False]
    inputs = inputs_of()
    assert inputs[StepName.ROUTES]["routing_moment"] == {  # type: ignore[index]
        "date": "2025-03-10",
        "time": "08:30",
        "arrive_by": True,
    }
    assert "routing_moment" not in inputs[StepName.AREA]  # type: ignore[operator]


def test_the_package_fingerprint_is_in_every_key() -> None:
    first = keys_of(inputs_of())
    other = keys_of(step_inputs(PARAMETERS, DATASET, PERIOD, "b" * 64, MANIFEST))

    assert all(other[step] != first[step] for step in BUILD_STEPS)


def test_the_graph_manifest_changes_the_keys_of_the_routes_and_what_follows() -> None:
    first = keys_of(inputs_of())
    other = keys_of(step_inputs(PARAMETERS, DATASET, PERIOD, FINGERPRINT, {**MANIFEST, "x": 1}))

    assert [other[s] == first[s] for s in BUILD_STEPS] == [True, True, False, False]
    assert graph_manifest_sha256(MANIFEST) != graph_manifest_sha256({**MANIFEST, "x": 1})


def test_the_snapshot_hashes_of_the_data_set_are_in_the_keys_that_read_them() -> None:
    dataset = replace(DATASET, gbfs=replace(DATASET.gbfs, sha256="1" * 64))
    first = keys_of(inputs_of())

    other = keys_of(step_inputs(PARAMETERS, dataset, PERIOD, FINGERPRINT, MANIFEST))

    # The bike-station snapshot is read by the area step, and the hubs read the area's key.
    assert all(other[step] != first[step] for step in BUILD_STEPS)


def test_without_a_fingerprint_no_key_exists() -> None:
    assert all(
        value is None for value in step_inputs(PARAMETERS, DATASET, PERIOD, None, MANIFEST).values()
    )
    assert canonical_inputs(StepName.AREA, PARAMETERS, DATASET, PERIOD, {}, None, MANIFEST) is None


def test_without_a_manifest_the_first_two_keys_exist_and_the_others_do_not() -> None:
    found = step_inputs(PARAMETERS, DATASET, PERIOD, FINGERPRINT, None)

    assert found[StepName.AREA] is not None
    assert found[StepName.HUBS] is not None
    assert found[StepName.ROUTES] is None
    assert found[StepName.TRAVELLERS_AND_BIKES] is None


def test_a_missing_upstream_key_means_no_key() -> None:
    assert (
        canonical_inputs(
            StepName.HUBS, PARAMETERS, DATASET, PERIOD, {StepName.AREA: None}, FINGERPRINT, MANIFEST
        )
        is None
    )


def test_a_plan_has_four_steps_in_order_with_their_periods() -> None:
    built = plan()

    assert [item.step for item in built.steps] == list(BUILD_STEPS)
    assert [item.position for item in built.steps] == [1, 2, 3, 4]
    assert [item.period_id for item in built.steps] == [None, None, PERIOD.id, PERIOD.id]
    assert all(item.action == "rebuilt" and item.causes == () for item in built.steps)


def test_a_step_whose_key_is_stored_is_kept() -> None:
    keys = [key for key in keys_of(inputs_of()).values() if key is not None]

    built = plan(stored=keys[:3])

    assert [item.action for item in built.steps] == ["kept", "kept", "kept", "rebuilt"]
    assert built.needs_trip_planner is False


def test_the_trip_planner_is_needed_unless_the_routes_step_is_kept() -> None:
    assert plan().needs_trip_planner is True


def test_with_no_fingerprint_every_step_is_rebuilt_with_a_null_key() -> None:
    built = plan(fingerprint=None)

    assert all(item.input_key is None and item.action == "rebuilt" for item in built.steps)
    assert built.package_missing is True


def test_with_no_manifest_the_routes_and_the_travellers_have_no_key() -> None:
    built = plan(manifest=None)

    assert [item.input_key is None for item in built.steps] == [False, False, True, True]
    assert [item.action for item in built.steps] == ["rebuilt"] * 4
    assert built.manifest_missing is True
    assert built.package_missing is False


def test_the_last_duration_is_the_one_given_for_the_step() -> None:
    built = plan(durations={StepName.ROUTES: 12.5})

    assert [item.last_duration_s for item in built.steps] == [None, None, 12.5, None]


def stored_inputs(**changes: Any) -> dict[StepName, Mapping[str, Any]]:
    return {step: value for step, value in inputs_of(**changes).items() if value is not None}


def test_without_a_version_to_start_from_there_is_no_cause() -> None:
    assert all(item.causes == () for item in plan(based_on=None).steps)


def test_a_step_the_start_version_never_stored_has_no_cause() -> None:
    assert all(item.causes == () for item in plan(based_on={}).steps)


def test_a_changed_parameter_is_the_cause_of_the_step_that_reads_it() -> None:
    built = plan(replace(PARAMETERS, seed=7), based_on=stored_inputs())

    assert [item.causes for item in built.steps] == [
        (),
        (),
        (),
        (Cause("parameter", ("seed",)),),
    ]


def test_an_upstream_parameter_is_inherited_by_the_steps_that_chain_its_key() -> None:
    built = plan(replace(PARAMETERS, clustering_buffer_m=150.0, seed=7), based_on=stored_inputs())

    assert [item.causes for item in built.steps] == [
        (),
        (Cause("parameter", ("clustering_buffer_m",)),),
        (Cause("parameter", ("clustering_buffer_m",)),),
        (Cause("parameter", ("clustering_buffer_m", "seed")),),
    ]


def test_new_city_data_is_a_cause() -> None:
    dataset = replace(DATASET, gtfs=replace(DATASET.gtfs, sha256="2" * 64))

    built = plan(dataset=dataset, based_on=stored_inputs())

    assert all(item.causes == (Cause("city_data"),) for item in built.steps)


def test_a_new_package_is_a_cause() -> None:
    built = plan(fingerprint="c" * 64, based_on=stored_inputs())

    assert all(item.causes == (Cause("package"),) for item in built.steps)


def test_a_new_trip_planner_graph_is_a_cause_of_the_routes_and_what_follows() -> None:
    built = plan(manifest={**MANIFEST, "x": 1}, based_on=stored_inputs())

    assert [item.causes for item in built.steps] == [
        (),
        (),
        (Cause("trip_planner_graph"),),
        (Cause("trip_planner_graph"),),
    ]


def test_several_causes_are_listed_in_a_fixed_order() -> None:
    built = plan(
        replace(PARAMETERS, min_od_distance_m=900.0),
        fingerprint="c" * 64,
        manifest={**MANIFEST, "x": 1},
        based_on=stored_inputs(),
    )

    assert built.step(StepName.ROUTES).causes == (
        Cause("parameter", ("min_od_distance_m",)),
        Cause("package"),
        Cause("trip_planner_graph"),
    )


def test_equal_keys_have_no_cause() -> None:
    inputs = inputs_of()[StepName.AREA]
    assert inputs is not None

    assert causes_between(inputs, inputs, [Cause("package")]) == ()
