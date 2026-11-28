from collections.abc import Callable

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.id_source import IdSource
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.domain.builds import ComponentUnavailable, DraftChanged, RunActive
from pricing_demo.domain.pricing_rules import PricingRuleBroken, check_pricing_rules
from pricing_demo.domain.pricing_versions import AlreadyRun, PricingVersionNotFound
from pricing_demo.domain.runs import (
    Run,
    RunKind,
    RunState,
    RunStep,
    StepName,
    Subject,
    SubjectType,
)
from pricing_demo.domain.system_status import SystemStatus

# A draft edited between the rule check and the seal is checked again on its new values; a
# draft that keeps changing faster than that is left to the client's next request.
ATTEMPTS = 3


class RunPricingVersion:
    """Validate a draft, seal it and queue its pricing run; or queue the run of a sealed version
    whose last run failed or was cancelled (the resume: done steps come back `kept`).

    The refusals come in this order: the version is unknown; a rule of the draft is broken; a
    run of the version is queued or running; the version already has its result; a component
    the run needs is not available (the solver, the package, the runner, storage; not the
    trip planner).
    """

    def __init__(
        self,
        pricing_versions: PricingVersions,
        system_status: Callable[[], SystemStatus],
        ids: IdSource,
        clock: Clock,
    ) -> None:
        self._pricing_versions = pricing_versions
        self._system_status = system_status
        self._ids = ids
        self._clock = clock

    def execute(self, version_id: str) -> Run:
        for _ in range(ATTEMPTS - 1):
            try:
                return self._attempt(version_id)
            except DraftChanged:
                continue
        return self._attempt(version_id)

    def _attempt(self, version_id: str) -> Run:
        version = self._pricing_versions.get(version_id)
        if version is None:
            raise PricingVersionNotFound(version_id)
        if version.status == "draft":
            failing = [result for result in check_pricing_rules(version.goals) if not result.passed]
            if failing:
                raise PricingRuleBroken(failing)
        latest = self._pricing_versions.latest_run(version_id)
        if latest is not None and latest.state in (RunState.QUEUED, RunState.RUNNING):
            raise RunActive(latest.id)
        if latest is not None and latest.state is RunState.SUCCEEDED:
            raise AlreadyRun(version_id)
        verdict = self._system_status().can_run_pricing
        if not verdict.allowed:
            raise ComponentUnavailable(verdict.reasons)
        # The version prices one period (ARCHITECTURE.md § 5.6).
        period_ids = self._pricing_versions.period_ids(version_id)
        if not period_ids:
            # Deleted since it was read.
            raise PricingVersionNotFound(version_id)
        period_id = period_ids[0]
        now = self._clock.now()
        run = Run(
            id=self._ids.new_run_id(),
            kind=RunKind.PRICING,
            subject=Subject(SubjectType.PRICING_VERSION, version_id),
            state=RunState.QUEUED,
            queued_at=now,
            steps=(
                RunStep(position=1, step=StepName.PRICING_MODEL, period=period_id),
                RunStep(position=2, step=StepName.TRAVELLER_SIMULATION, period=period_id),
            ),
        )
        if version.status == "draft":
            self._pricing_versions.queue_run(run, now, version.goals)
        else:
            self._pricing_versions.queue_run(run, None, None)
        return run
