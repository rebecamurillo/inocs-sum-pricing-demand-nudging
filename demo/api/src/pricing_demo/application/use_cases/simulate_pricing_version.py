from collections.abc import Callable

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.id_source import IdSource
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.simulations import LinkedSimulation, Simulations
from pricing_demo.domain.builds import ComponentUnavailable, RunActive
from pricing_demo.domain.pricing_versions import (
    NoResult,
    PricingVersionNotFound,
    SimulationCurrent,
)
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
from pricing_demo.domain.traveller_simulation import SimulationRule

SCHEMES = ("model_prices", "flat")


def has_rule(linked: LinkedSimulation, rule: SimulationRule) -> bool:
    """Whether the stored simulation ran under `rule`: the triple of id, version, parameters."""
    return (linked.rule_id, linked.rule_version, dict(linked.rule_parameters)) == (
        rule.id,
        rule.version,
        dict(rule.parameters),
    )


class SimulatePricingVersion:
    """Queue a run of kind `simulation` that simulates a version's stored solve again with the
    rule the live worker uses. No solve and no solver probe happen: the run holds the one step
    `traveller_simulation`, which reads the stored solve; the simulations it adds sit beside the
    older ones.

    The refusals come in this order: the version is unknown; a run of the version (any kind) is
    queued or running; the version has no succeeded pricing run; the worker and storage are not
    available (`can_simulate`; neither the solver nor the trip planner counts); both schemes
    already have a simulation under the current rule.
    """

    def __init__(
        self,
        pricing_versions: PricingVersions,
        simulations: Simulations,
        system_status: Callable[[], SystemStatus],
        ids: IdSource,
        clock: Clock,
    ) -> None:
        self._pricing_versions = pricing_versions
        self._simulations = simulations
        self._system_status = system_status
        self._ids = ids
        self._clock = clock

    def execute(self, version_id: str) -> Run:
        if self._pricing_versions.get(version_id) is None:
            raise PricingVersionNotFound(version_id)
        active = self._pricing_versions.active_run_id(version_id)
        if active is not None:
            raise RunActive(active)
        latest = self._pricing_versions.latest_run(version_id)
        if latest is None or latest.state is not RunState.SUCCEEDED:
            raise NoResult(version_id)
        status = self._system_status()
        verdict = status.can_simulate
        if not verdict.allowed:
            raise ComponentUnavailable(verdict.reasons)
        period_ids = self._pricing_versions.period_ids(version_id)
        if not period_ids:
            # Deleted since it was read.
            raise PricingVersionNotFound(version_id)
        period_id = period_ids[0]
        rule = status.simulation_rule
        if rule is not None and self._is_current(version_id, period_id, rule):
            raise SimulationCurrent(version_id)
        run = Run(
            id=self._ids.new_run_id(),
            kind=RunKind.SIMULATION,
            subject=Subject(SubjectType.PRICING_VERSION, version_id),
            state=RunState.QUEUED,
            queued_at=self._clock.now(),
            steps=(RunStep(position=1, step=StepName.TRAVELLER_SIMULATION, period=period_id),),
        )
        self._pricing_versions.queue_run(run, None, None)
        return run

    def _is_current(self, version_id: str, period_id: str, rule: SimulationRule) -> bool:
        current = {
            item.price_scheme
            for item in self._simulations.linked_of(version_id)
            if item.period_id == period_id and has_rule(item, rule)
        }
        return all(scheme in current for scheme in SCHEMES)
