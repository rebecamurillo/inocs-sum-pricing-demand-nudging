"""The counts of a built version, read from what the ingestion stored."""

from collections.abc import Mapping

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.route_failures import RouteFailures
from pricing_demo.domain.build_plan import BUILD_STEPS
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.read_model import RoutesSummary, headline_counts, routes_summary
from pricing_demo.domain.runs import STEP_NUMBERS, StepName


class BuiltCounts:
    def __init__(
        self, artifacts: Artifacts, read_model: ReadModel, route_failures: RouteFailures
    ) -> None:
        self._artifacts = artifacts
        self._read_model = read_model
        self._route_failures = route_failures

    def of(self, version_id: str) -> tuple[Mapping[str, Number] | None, RoutesSummary | None]:
        """The five headline numbers and the routes summary; both None until every step of
        the version is linked to an ingested artefact."""
        links = self._artifacts.links_of(version_id)
        if any(step not in links for step in BUILD_STEPS):
            return None, None
        counts = self._read_model.counts_of([links[step] for step in BUILD_STEPS])
        if any(links[step] not in counts for step in BUILD_STEPS):
            return None, None

        def of_step(step: StepName) -> Mapping[str, object]:
            return counts[links[step]]

        routes_artifact = self._artifacts.get(links[StepName.ROUTES])
        run_id = routes_artifact.run_id if routes_artifact else None
        failures = (
            self._route_failures.of_step(run_id, STEP_NUMBERS[StepName.ROUTES])
            if run_id is not None
            else []
        )
        routes = of_step(StepName.ROUTES)
        return (
            headline_counts(
                of_step(StepName.AREA),
                of_step(StepName.HUBS),
                routes,
                of_step(StepName.TRAVELLERS_AND_BIKES),
            ),
            routes_summary(routes, failures, run_id),
        )
