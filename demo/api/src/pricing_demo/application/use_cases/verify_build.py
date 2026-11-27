from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pricing_demo.application.build_planning import _context
from pricing_demo.application.errors import VersionNotBuilt
from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.city_preparation import CityPreparation, PreparationRequest
from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.application.ports.scratch_builds import ScratchBuilds
from pricing_demo.application.ports.step_executor import StopSignal
from pricing_demo.domain.build_plan import (
    BUILD_STEPS,
    STEP_OUTPUTS,
    STEP_UPSTREAM,
    STEP_UPSTREAM_FILES,
)
from pricing_demo.domain.build_verification import (
    BuildComparison,
    BuildDescription,
    Pair,
    compare_builds,
    instance_pair_contents,
    route_pair_contents,
)
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import StepName

STOPPED = "stopped"
STOPPED_REASON = "the rebuild was stopped"


@dataclass(frozen=True)
class VerifyResult:
    """The comparison, or the step that failed in the rebuild with its code and reason."""

    comparison: BuildComparison | None = None
    failure: tuple[StepName, str, str] | None = None


class VerifyBuild:
    """Rebuilds the four steps of a built version in a scratch folder, with reuse off, and
    compares the files and the hub pairs with the stored build. It writes no row: no artefact,
    link, read-model row, route failure or run."""

    def __init__(
        self,
        instances: CityInstances,
        datasets: CityDatasets,
        artifacts: Artifacts,
        files: ArtifactFiles,
        route_failures: RouteFailures,
        preparation: CityPreparation,
        scratch: ScratchBuilds,
    ) -> None:
        self._instances = instances
        self._datasets = datasets
        self._artifacts = artifacts
        self._files = files
        self._route_failures = route_failures
        self._preparation = preparation
        self._scratch = scratch

    def execute(self, version_id: str, stop: StopSignal) -> VerifyResult:
        version = self._instances.get_version(version_id)
        if version is None:
            raise InstanceVersionNotFound(version_id)
        dataset, period = _context(version, self._instances, self._datasets)
        links = self._artifacts.links_of(version_id)
        if any(step not in links for step in BUILD_STEPS):
            raise VersionNotBuilt(version_id)
        stored = self._stored(links)
        root = self._scratch.create()
        failed: set[Pair] = set()
        folders: dict[StepName, Path] = {}
        hashes: dict[StepName, dict[str, str]] = {}
        try:
            for step in BUILD_STEPS:
                folder = self._scratch.step_dir(root, step)
                folders[step] = folder
                wanted = STEP_UPSTREAM_FILES[step]
                # Reuse is off: the upstream files are the rebuilt ones, never the stored ones.
                for upstream in STEP_UPSTREAM[step]:
                    names = [name for name in STEP_OUTPUTS[upstream] if name in wanted]
                    self._scratch.copy(folders[upstream], names, folder)
                request = PreparationRequest(
                    f"verify-{root.name}", step, folder, version.parameters, dataset, period
                )
                outcome = self._preparation.prepare(
                    request,
                    lambda done, total: None,
                    stop,
                    lambda failure: failed.add((failure.origin_hub, failure.destination_hub)),
                )
                if outcome.stopped:
                    return VerifyResult(failure=(step, STOPPED, STOPPED_REASON))
                if outcome.failure_code is not None:
                    reason = outcome.failure_reason or ""
                    return VerifyResult(failure=(step, outcome.failure_code, reason))
                try:
                    hashes[step] = self._scratch.hashes(folder, STEP_OUTPUTS[step])
                except FileNotFoundError as error:
                    return VerifyResult(failure=(step, STAGE_ERROR, str(error)))
            try:
                rebuilt = self._describe(
                    hashes,
                    frozenset(failed),
                    self._scratch.read_json(folders[StepName.ROUTES], "od_routes.json"),
                    self._scratch.read_json(folders[StepName.ROUTES], "od_geometry.json"),
                    self._scratch.read_json(
                        folders[StepName.TRAVELLERS_AND_BIKES], "Instance_1.json"
                    ),
                )
            except ValueError as error:
                return VerifyResult(failure=(StepName.ROUTES, STAGE_ERROR, str(error)))
            return VerifyResult(comparison=compare_builds(stored, rebuilt))
        finally:
            self._scratch.remove(root)

    def _stored(self, links: Mapping[StepName, str]) -> BuildDescription:
        found = {step: self._artifacts.get(links[step]) for step in BUILD_STEPS}
        if any(artifact is None for artifact in found.values()):
            raise VersionNotBuilt("the version")  # pragma: no cover - a link has its artefact
        artifacts = {step: artifact for step, artifact in found.items() if artifact is not None}
        routes = artifacts[StepName.ROUTES]
        failures = self._route_failures.of_run(routes.run_id) if routes.run_id else []
        read = self._files.read_json
        travellers = artifacts[StepName.TRAVELLERS_AND_BIKES]
        return self._describe(
            {
                step: {item.name: item.sha256 for item in artifact.files}
                for step, artifact in artifacts.items()
            },
            frozenset((item.origin_hub, item.destination_hub) for item, _ in failures),
            read(routes.path, "od_routes.json"),
            read(routes.path, "od_geometry.json"),
            read(travellers.path, "Instance_1.json"),
        )

    @staticmethod
    def _describe(
        hashes: Mapping[StepName, Mapping[str, str]],
        failed: frozenset[Pair],
        od_routes: Any,
        od_geometry: Any,
        instance: Any,
    ) -> BuildDescription:
        return BuildDescription(
            hashes,
            failed,
            route_pair_contents(od_routes, od_geometry),
            instance_pair_contents(instance),
        )
