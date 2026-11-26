"""The plan of a build: the input key of each of the four steps, whether the step is kept or
rebuilt, and why it is rebuilt (ARCHITECTURE.md § 4.3).

A step's key is the sha256 of a canonical JSON of what the step reads, so an unchanged input
finds the stored artefact again whichever version asks for it. Pure: no I/O.
"""

import hashlib
import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import PARAMETER_NAMES, InstanceParameters, InstancePeriod
from pricing_demo.domain.runs import StepName

BUILD_STEPS = (
    StepName.AREA,
    StepName.HUBS,
    StepName.ROUTES,
    StepName.TRAVELLERS_AND_BIKES,
)

# The parameters each step reads (`pipeline.py`, `config.py`). `otp_workers` is not one of them:
# the routes do not depend on it (ARCHITECTURE.md § 4.6).
STEP_PARAMETERS: Mapping[StepName, tuple[str, ...]] = {
    StepName.AREA: ("center_lat", "center_lon", "radius_m"),
    StepName.HUBS: ("clustering_threshold_m", "clustering_buffer_m"),
    StepName.ROUTES: ("min_od_distance_m",),
    StepName.TRAVELLERS_AND_BIKES: (
        "seed",
        "fixed_capacity",
        "min_demand",
        "max_demand",
        "min_inventory_pct",
        "max_inventory_pct",
        "min_park_time_min",
        "max_park_time_min",
    ),
}

# The steps whose artefacts a step reads.
STEP_UPSTREAM: Mapping[StepName, tuple[StepName, ...]] = {
    StepName.AREA: (),
    StepName.HUBS: (StepName.AREA,),
    StepName.ROUTES: (StepName.HUBS,),
    StepName.TRAVELLERS_AND_BIKES: (StepName.AREA, StepName.HUBS, StepName.ROUTES),
}

# The snapshot hashes each step reads.
STEP_SNAPSHOTS: Mapping[StepName, tuple[str, ...]] = {
    StepName.AREA: ("gtfs_sha256", "gbfs_sha256"),
    StepName.HUBS: ("gtfs_sha256",),
    StepName.ROUTES: ("graph_manifest_sha256",),
    StepName.TRAVELLERS_AND_BIKES: (),
}

# The files a step writes, under the names the package gives them (ARCHITECTURE.md § 4.1).
STEP_OUTPUTS: Mapping[StepName, tuple[str, ...]] = {
    StepName.AREA: ("stations.json",),
    StepName.HUBS: ("hubs.geojson", "stations_hubs.geojson", "hub_polygons.geojson"),
    StepName.ROUTES: ("od_routes.json", "od_geometry.json"),
    StepName.TRAVELLERS_AND_BIKES: ("Instance_1.json",),
}

# The upstream files a step needs in its working directory, under the names the package
# expects (`pipeline.py:30-31, 36, 52-58`).
STEP_UPSTREAM_FILES: Mapping[StepName, tuple[str, ...]] = {
    StepName.AREA: (),
    StepName.HUBS: ("stations.json",),
    StepName.ROUTES: ("hubs.geojson",),
    StepName.TRAVELLERS_AND_BIKES: ("od_routes.json", "stations.json", "hubs.geojson"),
}

# Steps 3 and 4 depend on the routing moment of the period.
PERIOD_STEPS = (StepName.ROUTES, StepName.TRAVELLERS_AND_BIKES)

CauseKind = Literal["parameter", "city_data", "package", "trip_planner_graph"]
CAUSE_ORDER: tuple[CauseKind, ...] = ("parameter", "city_data", "package", "trip_planner_graph")
CITY_DATA_SNAPSHOTS = ("gtfs_sha256", "gbfs_sha256")


def _normal(value: Any) -> Any:
    """20 and 20.0 are the same value (`what_changes` treats them so): both hash as 20."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def input_key(inputs: Mapping[str, Any]) -> str:
    return sha256_of(inputs)


def graph_manifest_sha256(manifest: Mapping[str, object]) -> str:
    return sha256_of(manifest)


def canonical_inputs(
    step: StepName,
    parameters: InstanceParameters,
    dataset: CityDataset,
    period: InstancePeriod,
    upstream_keys: Mapping[StepName, str | None],
    package_fingerprint: str | None,
    graph_manifest: Mapping[str, object] | None,
) -> dict[str, Any] | None:
    """What the step reads, or None when something it needs is not known yet: the package
    fingerprint, the trip planner's graph manifest (steps 3 and 4) or an upstream key."""
    if package_fingerprint is None:
        return None
    upstream = {name.value: upstream_keys.get(name) for name in STEP_UPSTREAM[step]}
    if any(key is None for key in upstream.values()):
        return None
    if step in PERIOD_STEPS and graph_manifest is None:
        return None
    values = parameters.as_dict()
    snapshots: dict[str, str] = {}
    for name in STEP_SNAPSHOTS[step]:
        if name == "gtfs_sha256":
            snapshots[name] = dataset.gtfs.sha256
        elif name == "gbfs_sha256":
            snapshots[name] = dataset.gbfs.sha256
        else:
            assert graph_manifest is not None
            snapshots[name] = graph_manifest_sha256(graph_manifest)
    inputs: dict[str, Any] = {
        "step": step.value,
        "parameters": {name: _normal(values[name]) for name in STEP_PARAMETERS[step]},
        "upstream": upstream,
        "snapshots": snapshots,
        "package_fingerprint": package_fingerprint,
    }
    if step in PERIOD_STEPS:
        inputs["routing_moment"] = {
            "date": period.routing_date.isoformat(),
            "time": period.routing_time.strftime("%H:%M"),
            "arrive_by": period.arrive_by,
        }
    return inputs


@dataclass(frozen=True)
class Cause:
    kind: CauseKind
    parameters: tuple[str, ...] = ()


def _own_causes(current: Mapping[str, Any], before: Mapping[str, Any]) -> set[Cause]:
    causes: set[Cause] = set()
    old_values, new_values = before.get("parameters", {}), current["parameters"]
    changed = tuple(
        name
        for name in PARAMETER_NAMES
        if name in new_values and _normal(old_values.get(name)) != _normal(new_values[name])
    )
    if changed:
        causes.add(Cause("parameter", changed))
    old_snapshots, new_snapshots = before.get("snapshots", {}), current["snapshots"]
    if any(old_snapshots.get(name) != new_snapshots.get(name) for name in CITY_DATA_SNAPSHOTS):
        causes.add(Cause("city_data"))
    if old_snapshots.get("graph_manifest_sha256") != new_snapshots.get("graph_manifest_sha256"):
        causes.add(Cause("trip_planner_graph"))
    if before.get("package_fingerprint") != current["package_fingerprint"]:
        causes.add(Cause("package"))
    return causes


def causes_between(
    current_inputs: Mapping[str, Any],
    based_on_inputs: Mapping[str, Any],
    upstream_causes: Collection[Cause] = (),
) -> tuple[Cause, ...]:
    """Why a step's key differs from the key of the same step of the version it is based on.

    Equal keys have no cause. A changed parameter names the parameters, a changed timetable or
    bike-station snapshot is `city_data`, a changed fingerprint is `package`, a changed graph
    manifest is `trip_planner_graph`; a step also carries the causes of the upstream steps its
    key chains, whose parameter names are merged into one cause.
    """
    if input_key(current_inputs) == input_key(based_on_inputs):
        return ()
    found = _own_causes(current_inputs, based_on_inputs) | set(upstream_causes)
    names = {name for cause in found if cause.kind == "parameter" for name in cause.parameters}
    merged = [
        Cause("parameter", tuple(name for name in PARAMETER_NAMES if name in names))
        if kind == "parameter"
        else Cause(kind)
        for kind in CAUSE_ORDER
        if (kind == "parameter" and names) or Cause(kind) in found
    ]
    return tuple(merged)


@dataclass(frozen=True)
class PlannedStep:
    step: StepName
    position: int
    period_id: str | None
    input_key: str | None
    inputs: Mapping[str, Any] | None
    action: Literal["kept", "rebuilt"]
    causes: tuple[Cause, ...]
    last_duration_s: float | None


@dataclass(frozen=True)
class BuildPlan:
    steps: tuple[PlannedStep, ...]
    package_missing: bool = False
    manifest_missing: bool = False

    def step(self, name: StepName) -> PlannedStep:
        return next(item for item in self.steps if item.step is name)

    @property
    def needs_trip_planner(self) -> bool:
        """The trip planner is needed unless the routes step is kept."""
        return self.step(StepName.ROUTES).action != "kept"


def step_inputs(
    parameters: InstanceParameters,
    dataset: CityDataset,
    period: InstancePeriod,
    package_fingerprint: str | None,
    graph_manifest: Mapping[str, object] | None,
) -> dict[StepName, dict[str, Any] | None]:
    """The canonical inputs of the four steps, each with the keys of the steps before it."""
    keys: dict[StepName, str | None] = {}
    found: dict[StepName, dict[str, Any] | None] = {}
    for step in BUILD_STEPS:
        inputs = canonical_inputs(
            step, parameters, dataset, period, keys, package_fingerprint, graph_manifest
        )
        found[step] = inputs
        keys[step] = input_key(inputs) if inputs is not None else None
    return found


def plan_build(
    parameters: InstanceParameters,
    dataset: CityDataset,
    period: InstancePeriod,
    package_fingerprint: str | None,
    graph_manifest: Mapping[str, object] | None,
    stored_keys: Collection[str],
    based_on_inputs: Mapping[StepName, Mapping[str, Any]] | None,
    durations: Mapping[StepName, float | None],
) -> BuildPlan:
    """The four steps with their keys; a step is kept when its key is stored, and a step with
    no key yet (the fingerprint or the manifest is unknown) is rebuilt."""
    inputs_by_step = step_inputs(parameters, dataset, period, package_fingerprint, graph_manifest)
    planned: list[PlannedStep] = []
    causes_by_step: dict[StepName, tuple[Cause, ...]] = {}
    for position, step in enumerate(BUILD_STEPS, start=1):
        inputs = inputs_by_step[step]
        key = input_key(inputs) if inputs is not None else None
        before = (based_on_inputs or {}).get(step)
        causes: tuple[Cause, ...] = ()
        if inputs is not None and before is not None:
            upstream = [c for up in STEP_UPSTREAM[step] for c in causes_by_step[up]]
            causes = causes_between(inputs, before, upstream)
        causes_by_step[step] = causes
        planned.append(
            PlannedStep(
                step=step,
                position=position,
                period_id=period.id if step in PERIOD_STEPS else None,
                input_key=key,
                inputs=inputs,
                action="kept" if key is not None and key in stored_keys else "rebuilt",
                causes=causes,
                last_duration_s=durations.get(step),
            )
        )
    plan = BuildPlan(tuple(planned))
    return BuildPlan(
        plan.steps,
        package_missing=package_fingerprint is None,
        manifest_missing=graph_manifest is None and plan.step(StepName.ROUTES).action == "rebuilt",
    )
