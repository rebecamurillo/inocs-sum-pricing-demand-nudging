"""A pricing rig: a built fake city in memory, and the worker's two pricing steps on the
in-memory adapters, run through the real `ProcessNextRun`."""

from dataclasses import replace
from pathlib import Path

from pricing_demo.application.ports.traveller_simulation import TravellerSimulation
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.run_pricing_step import PricingModelStepExecutor
from pricing_demo.application.use_cases.run_simulation_step import TravellerSimulationStepExecutor
from pricing_demo.domain.pricing_versions import PricingGoals, new_draft_goals
from pricing_demo.domain.runs import Run, RunState, StepName
from pricing_demo.domain.system_status import ComponentName
from pricing_demo.domain.traveller_simulation import BalancedScore
from pricing_demo.infrastructure.artifact_store.local import LocalArtifactStore
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from pricing_demo.infrastructure.fakes.worker_registry import InMemoryWorkerRegistry
from tests.support.builds import SLUG, MemoryBuilds, build_fake_city
from tests.support.runs import T0

INSTANCE_VERSION = f"{SLUG}.v1"
PERIOD = f"{INSTANCE_VERSION}.mon-08"


class PricingRig:
    """The rig's built instance `geneva-3km.v1`, its pricing versions and the worker's steps."""

    def __init__(self, folder: Path, rule: TravellerSimulation | None = None) -> None:
        self.rig = MemoryBuilds()
        self.rig.add_draft()
        build = build_fake_city(self.rig, folder)
        self.rig.runs.update(build, lambda run: replace(run, state=RunState.SUCCEEDED))
        self.files = LocalArtifactStore(folder)
        self.settings = InMemoryFakeSettings()
        self.reports = InMemoryComponentReports()
        self.registry = StepRegistry()
        self.model = PricingModelStepExecutor(
            FakePricingSolver(self.settings),
            FakeProbe(ComponentName.SOLVER, self.settings),
            self.reports,
            "w-1",
            self.files,
            self.rig.artifacts,
            self.rig.solves,
            self.rig.pricing,
            self.rig.runs,
            self.rig.sources,
            self.rig.clock,
        )
        self.registry.register(StepName.PRICING_MODEL, self.model, self.model)
        self.use_rule(rule or BalancedScore())
        identity = WorkerIdentity("w-1", "host", 1, T0)
        self.process = ProcessNextRun(
            self.rig.runs,
            self.registry,
            InMemoryWorkerRegistry(),
            identity,
            self.rig.clock,
            self.rig.waiter,
        )

    def use_rule(self, rule: TravellerSimulation) -> TravellerSimulationStepExecutor:
        self.simulation = TravellerSimulationStepExecutor(
            rule,
            self.rig.pricing,
            self.rig.artifacts,
            self.rig.solves,
            self.rig.simulations,
            self.rig.read_model,
            self.rig.runs,
            self.rig.clock,
            "0.1.0",
        )
        self.registry.register(StepName.TRAVELLER_SIMULATION, self.simulation, self.simulation)
        return self.simulation

    def version(self, **changes: float) -> str:
        goals: PricingGoals = new_draft_goals(None).replacing(changes)
        return self.rig.pricing.create_draft(INSTANCE_VERSION, None, goals, PERIOD, None, T0).id

    def run(self, version_id: str) -> Run:
        """Queue the version's pricing run, have the worker process it, and return it as stored."""
        queued = self.rig.run_pricing.execute(version_id)
        assert self.process.execute() is True
        return self.stored(queued.id)

    def stored(self, run_id: str) -> Run:
        run = self.rig.runs.get(run_id)
        assert run is not None
        return run
