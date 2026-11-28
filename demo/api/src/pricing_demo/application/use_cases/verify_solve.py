import uuid
from dataclasses import dataclass

from pricing_demo.application.errors import SolveNotFound, SolveNotVerifiable
from pricing_demo.application.ports.artifact_files import ArtifactFiles
from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.pricing_solver import PricingSolver, SolveRequest
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.simulations import Simulations, StoredSimulationRows
from pricing_demo.application.ports.solves import Solves
from pricing_demo.application.ports.step_executor import StopSignal
from pricing_demo.domain.pricing_keys import FIXED_SOLVER_INPUTS, SOLVER_GOALS
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.simulation_inputs import simulation_instance_from
from pricing_demo.domain.solve_verification import (
    VERIFY_RUN_PREFIX,
    SolveVerification,
    TableComparison,
    compare_simulation_rows,
    compare_solve_rows,
    simulation_rows,
)
from pricing_demo.domain.solves import model_bike_prices
from pricing_demo.domain.traveller_simulation import (
    RULE_ID,
    BalancedScore,
    FlatPrice,
    ModelPrices,
    PriceScheme,
)

INSTANCE_FILE = "Instance_1.json"
STOPPED_REASON = "the re-run was stopped"


@dataclass(frozen=True)
class VerifySolveResult:
    """The comparison, or the reason the re-solve did not end with a solve (code and reason)."""

    verification: SolveVerification | None = None
    failure: tuple[str, str] | None = None


class VerifySolve:
    """Re-solves a stored solve in a scratch folder and re-simulates each simulation stored for
    it, then compares the rows with the stored ones. It writes no row: no solve, artefact,
    simulation or link."""

    def __init__(
        self,
        solves: Solves,
        pricing_versions: PricingVersions,
        simulations: Simulations,
        artifacts: Artifacts,
        files: ArtifactFiles,
        read_model: ReadModel,
        solver: PricingSolver,
        clock: Clock,
    ) -> None:
        self._solves = solves
        self._pricing_versions = pricing_versions
        self._simulations = simulations
        self._artifacts = artifacts
        self._files = files
        self._read_model = read_model
        self._solver = solver
        self._clock = clock

    def execute(self, solve_id: str, stop: StopSignal) -> VerifySolveResult:
        ref = self._solves.find(solve_id)
        if ref is None:
            raise SolveNotFound(solve_id)
        version = self._pricing_versions.get(ref.pricing_version_id)
        record = self._solves.solve_of(ref.pricing_version_id, ref.period_id)
        stored_rows = self._solves.rows(ref.key)
        if version is None or record is None or not stored_rows:
            raise SolveNotVerifiable(solve_id, "its rows are not stored")
        instance_key = self._artifacts.links_of(version.instance_version_id).get(
            StepName.TRAVELLERS_AND_BIKES
        )
        if instance_key is None:
            raise SolveNotVerifiable(solve_id, "the instance version has no stored build")
        stored = [
            found
            for link in self._simulations.links_of(version.id)
            if link.period_id == ref.period_id
            if (found := self._simulations.stored_of(link.simulation_key)) is not None
        ]
        if not stored:
            raise SolveNotVerifiable(solve_id, "no simulation is stored for it")
        rules = [(item, self._rule(solve_id, item)) for item in stored]

        run_id = f"{VERIFY_RUN_PREFIX}{uuid.uuid4().hex}"
        working = self._files.working_dir(run_id, StepName.PRICING_MODEL)
        try:
            self._files.copy_upstream(
                StepName.TRAVELLERS_AND_BIKES, instance_key, [INSTANCE_FILE], working
            )
            values = version.goals.as_dict()
            started = self._clock.now()
            outcome = self._solver.solve(
                SolveRequest(
                    run_id,
                    working,
                    {name: values[name] for name in SOLVER_GOALS},
                    dict(FIXED_SOLVER_INPUTS),
                    record.provenance.package_fingerprint,
                ),
                stop,
            )
            resolve_s = (self._clock.now() - started).total_seconds()
            if outcome.stopped:
                return VerifySolveResult(failure=("stopped", STOPPED_REASON))
            if outcome.failure_code is not None or outcome.solve is None:
                return VerifySolveResult(
                    failure=(
                        outcome.failure_code or STAGE_ERROR,
                        outcome.failure_reason or "the solver returned no solve",
                    )
                )
            tables: list[TableComparison] = [
                compare_solve_rows(stored_rows, list(outcome.solve.rows))
            ]
            durations = [("re-solve", resolve_s)]
            for item, rule in rules:
                if stop.is_set():
                    return VerifySolveResult(failure=("stopped", STOPPED_REASON))
                label = f"{item.scheme_kind} ({rule.rule_id} v{rule.rule_version})"
                started = self._clock.now()
                rerun = rule.simulate(
                    simulation_instance_from(
                        self._read_model.hub_pairs(item.instance_key),
                        self._read_model.route_options(item.instance_key),
                        self._read_model.station_bikes(item.instance_key),
                        self._read_model.option_station_deltas(item.instance_key),
                    ),
                    self._scheme(solve_id, item),
                )
                durations.append(
                    (f"re-simulation {label}", (self._clock.now() - started).total_seconds())
                )
                tables += compare_simulation_rows(label, item.rows, simulation_rows(rerun))
            return VerifySolveResult(SolveVerification(tuple(tables), tuple(durations)))
        finally:
            # The whole run folder `runs/verify-{uuid}/`, on every path.
            self._files.discard(working.parent)

    @staticmethod
    def _rule(solve_id: str, item: StoredSimulationRows) -> BalancedScore:
        rule = item.rule
        if rule.id != RULE_ID:
            raise SolveNotVerifiable(
                solve_id, f"the worker cannot build the rule {rule.id} version {rule.version}"
            )
        try:
            return BalancedScore(
                rule.parameters["price_weight"],
                rule.parameters["time_weight"],
                rule.id,
                rule.version,
            )
        except KeyError as error:
            raise SolveNotVerifiable(
                solve_id, f"the rule {rule.id} has no parameter {error.args[0]}"
            ) from error

    def _scheme(self, solve_id: str, item: StoredSimulationRows) -> PriceScheme:
        """The prices the stored simulation read: the stored solve's rows, or its flat price."""
        if item.scheme_kind == "model_prices":
            if item.solve_key is None:
                raise SolveNotVerifiable(solve_id, "a model-price simulation names no solve")
            return ModelPrices(
                model_bike_prices(self._solves.rows(item.solve_key)),
                item.pt_fare_chf,
                item.car_parking_fee_chf,
            )
        if item.flat_price_amount_chf is None:
            raise SolveNotVerifiable(solve_id, "a flat simulation names no price")
        return FlatPrice(item.flat_price_amount_chf, item.pt_fare_chf, item.car_parking_fee_chf)
