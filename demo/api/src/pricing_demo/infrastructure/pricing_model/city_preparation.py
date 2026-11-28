"""The real `CityPreparation`: the four steps run the package in a stage child.

This is where the product's parameter names meet the package's (`PipelineConfig`,
`InstanceParams`). The routes step also reads the child's `progress.jsonl` while it runs: the
queries done, the pairs found and each failed query.
"""

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

from pricing_demo.application.ports.city_preparation import (
    PreparationRequest,
    Progress,
    RouteFailed,
    ignore_route_failure,
)
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.city_instances import otp_timestamp
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.pricing_model.routes_progress import ProgressFile, RoutesProgress
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import PROGRESS_FILE, StageSpec, StageStep

STAGE_STEP_OF: dict[StepName, StageStep] = {
    StepName.AREA: "area",
    StepName.HUBS: "hubs",
    StepName.ROUTES: "routes",
    StepName.TRAVELLERS_AND_BIKES: "travellers_and_bikes",
}


class PackageCityPreparation:
    def __init__(
        self,
        data_dir: Path,
        child: StageChild,
        otp_url: str,
        otp_workers: int = 4,
        retries: int = 3,
        retry_wait_s: float = 2.0,
    ) -> None:
        # Absolute: the child runs in the step's working directory, so a path relative to the
        # worker's own directory (the default `var/data`) would not resolve there.
        self._data_dir = data_dir.absolute()
        self._child = child
        self._otp_url = otp_url
        self._otp_workers = otp_workers
        self._retries = retries
        self._retry_wait_s = retry_wait_s

    def prepare(
        self,
        request: PreparationRequest,
        progress: Progress,
        stop: StopSignal,
        route_failed: RouteFailed = ignore_route_failure,
    ) -> StepOutcome:
        stage = STAGE_STEP_OF[request.step]
        spec = self._spec(request, stage)
        if stage != "routes":
            return self._child.run(spec, stop)
        return self._run_routes(spec, request, progress, route_failed, stop)

    def _run_routes(
        self,
        spec: StageSpec,
        request: PreparationRequest,
        progress: Progress,
        route_failed: RouteFailed,
        stop: StopSignal,
    ) -> StepOutcome:
        state = RoutesProgress(self._retries)
        file = ProgressFile(request.working_dir.absolute() / PROGRESS_FILE)
        reported = (0, 0)

        def read() -> None:
            nonlocal reported
            for record in file.read_new():
                for failure in state.feed(record):
                    route_failed(failure)
            if (state.done, state.total) != reported:
                reported = (state.done, state.total)
                progress(state.done, state.total)

        outcome = self._child.run(spec, stop, read)
        if outcome.failure_code is not None or outcome.stopped:
            return outcome
        counts = {
            "hub_pairs_requested": state.total,
            "hub_pairs_removed": state.removed,
            "retries": self._retries,
        }
        return replace(outcome, counts=counts)

    def _spec(self, request: PreparationRequest, stage: StageStep) -> StageSpec:
        values = request.parameters
        pipeline: dict[str, Any] = {}
        instance: dict[str, Any] = {}
        if stage in ("area", "hubs"):
            pipeline = {
                "center_lat": values.center_lat,
                "center_lon": values.center_lon,
                "radius_m": values.radius_m,
                "gtfs_path": str(self._data_dir / request.dataset.gtfs.file),
                "gbfs_path": str(self._data_dir / request.dataset.gbfs.file),
            }
        if stage == "hubs":
            pipeline["clustering_threshold_m"] = values.clustering_threshold_m
            pipeline["clustering_buffer_m"] = values.clustering_buffer_m
        if stage == "travellers_and_bikes":
            pipeline = {
                "center_lat": values.center_lat,
                "center_lon": values.center_lon,
                "radius_m": values.radius_m,
                "gtfs_path": str(self._data_dir / request.dataset.gtfs.file),
                "seed": values.seed,
            }
            instance = {
                "fixed_capacity": values.fixed_capacity,
                "min_demand": values.min_demand,
                "max_demand": values.max_demand,
                "min_inventory_pct": values.min_inventory_pct,
                "max_inventory_pct": values.max_inventory_pct,
                "min_park_time": values.min_park_time_min,
                "max_park_time": values.max_park_time_min,
            }
        routes: dict[str, Any] = {}
        if stage == "routes":
            moment = request.period
            pipeline = {
                "center_lat": values.center_lat,
                "center_lon": values.center_lon,
                "radius_m": values.radius_m,
                "gtfs_path": str(self._data_dir / request.dataset.gtfs.file),
                "min_od_distance_m": values.min_od_distance_m,
                "otp_url": self._otp_url,
                "otp_workers": self._otp_workers,
                "otp_timestamp": otp_timestamp(moment.routing_date, moment.routing_time),
            }
            routes = {
                "retries": self._retries,
                "retry_wait_s": self._retry_wait_s,
                "routing_date": moment.routing_date.isoformat(),
            }
        return StageSpec(
            stage, str(request.working_dir.absolute()), os.getpid(), pipeline, instance, routes
        )
