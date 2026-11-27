"""The real `CityPreparation`: steps 1, 2 and 4 run the package in a stage child.

This is where the product's parameter names meet the package's (`PipelineConfig`,
`InstanceParams`). The routes step has no real adapter yet (story 2-8).
"""

import os
from pathlib import Path
from typing import Any

from pricing_demo.application.ports.city_preparation import (
    PreparationRequest,
    Progress,
    RouteFailed,
    ignore_route_failure,
)
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import StageSpec, StageStep

STAGE_STEP_OF: dict[StepName, StageStep] = {
    StepName.AREA: "area",
    StepName.HUBS: "hubs",
    StepName.TRAVELLERS_AND_BIKES: "travellers_and_bikes",
}


class PackageCityPreparation:
    def __init__(self, data_dir: Path, child: StageChild) -> None:
        # Absolute: the child runs in the step's working directory, so a path relative to the
        # worker's own directory (the default `var/data`) would not resolve there.
        self._data_dir = data_dir.absolute()
        self._child = child

    def prepare(
        self,
        request: PreparationRequest,
        progress: Progress,
        stop: StopSignal,
        route_failed: RouteFailed = ignore_route_failure,
    ) -> StepOutcome:
        stage = STAGE_STEP_OF.get(request.step)
        if stage is None:
            return StepOutcome.failed(STAGE_ERROR, "the routes step has no real adapter yet")
        return self._child.run(self._spec(request, stage), stop)

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
        return StageSpec(
            stage, str(request.working_dir.absolute()), os.getpid(), pipeline, instance
        )
