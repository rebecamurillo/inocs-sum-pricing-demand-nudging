import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.pricing_versions import PricingVersions
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.application.ports.simulations import (
    SimulationLink,
    Simulations,
    StoredSimulation,
)
from pricing_demo.application.ports.solves import Solves
from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.application.ports.traveller_simulation import TravellerSimulation
from pricing_demo.application.run_step_writes import write_kept
from pricing_demo.domain.failure_codes import SIMULATION_CHECK_FAILED
from pricing_demo.domain.pricing_keys import KEPT_SIMULATION_REASON, simulation_key
from pricing_demo.domain.pricing_versions import PricingVersion, PricingVersionNotFound
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import Run, RunStep, StepName
from pricing_demo.domain.simulation_inputs import simulation_instance_from
from pricing_demo.domain.solves import model_bike_prices
from pricing_demo.domain.traveller_simulation import (
    FlatPrice,
    ModelPrices,
    PriceScheme,
    SimulationCheckFailed,
)

logger = logging.getLogger(__name__)

NO_INSTANCE_REASON = "the instance version has no stored build"
NO_SOLVE_REASON = "the pricing model's solve of this version is not stored"
SCHEMES = ("model_prices", "flat")


@dataclass(frozen=True)
class _Context:
    rule: TravellerSimulation  # read once per keep or execute: keys, outputs and links agree
    version: PricingVersion
    period_id: str
    instance_key: str
    solve_key: str
    keys: dict[str, str]  # the simulation key of each scheme


class TravellerSimulationStepExecutor:
    """Runs and keeps the traveller simulation step of a pricing run (`StepExecutor` and
    `StepKeeper`): the rule simulates the period's travellers twice, with the model's prices
    and with the flat price, and the two simulations are stored with their links.

    A simulation stored under the same key (the same instance, rule, prices and solve) is
    reused, so versions of one period with the same flat price share one flat simulation.

    The rule is read from a callable, once per `keep` and once per `execute`, so a rule the
    worker's composition root changes simulates a stored version again under new keys and links
    beside the old ones.
    """

    def __init__(
        self,
        rule: Callable[[], TravellerSimulation],
        pricing_versions: PricingVersions,
        artifacts: Artifacts,
        solves: Solves,
        simulations: Simulations,
        read_model: ReadModel,
        queue: RunQueue,
        clock: Clock,
        demonstrator_version: str,
    ) -> None:
        self._rule = rule
        self._pricing_versions = pricing_versions
        self._artifacts = artifacts
        self._solves = solves
        self._simulations = simulations
        self._read_model = read_model
        self._queue = queue
        self._clock = clock
        self._demonstrator_version = demonstrator_version

    def keep(self, run: Run, step: RunStep) -> bool:
        context = self._context(run, step)
        if isinstance(context, str):
            return False
        if not all(self._simulations.is_stored(key) for key in context.keys.values()):
            return False
        self._simulations.store([], self._links(context))
        write_kept(self._queue, run.id, step, KEPT_SIMULATION_REASON, {})
        return True

    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        context = self._context(run, step)
        if isinstance(context, str):
            return StepOutcome.failed(STAGE_ERROR, context)
        started = self._clock.now()
        missing = [name for name in SCHEMES if not self._simulations.is_stored(context.keys[name])]
        new: list[StoredSimulation] = []
        counts: dict[str, Any] = {"reused": [name for name in SCHEMES if name not in missing]}
        try:
            instance = simulation_instance_from(
                self._read_model.hub_pairs(context.instance_key),
                self._read_model.route_options(context.instance_key),
                self._read_model.station_bikes(context.instance_key),
                self._read_model.option_station_deltas(context.instance_key),
            )
            for name in missing:
                if stop.is_set():
                    return StepOutcome.stopped_on_signal()
                outputs = context.rule.simulate(instance, self._scheme(name, context))
                goals = context.version.goals
                new.append(
                    StoredSimulation(
                        key=context.keys[name],
                        instance_key=context.instance_key,
                        period_id=context.period_id,
                        outputs=outputs,
                        scheme_kind=name,  # type: ignore[arg-type]
                        solve_key=context.solve_key if name == "model_prices" else None,
                        flat_price_kind=goals.flat_price_kind if name == "flat" else None,
                        flat_price_amount_chf=(
                            float(goals.flat_price_per_ride_chf) if name == "flat" else None
                        ),
                        pt_fare_chf=float(goals.pt_fare_chf),
                        car_parking_fee_chf=float(goals.car_parking_fee_chf),
                        demonstrator_version=self._demonstrator_version,
                        duration_s=(self._clock.now() - started).total_seconds(),
                        created_at=self._clock.now(),
                    )
                )
                counts[name] = {
                    "travellers": sum(outputs.travellers_per_mode.values()) + outputs.unserved,
                    "displaced": outputs.displaced,
                    "bike_rides": outputs.bike_rides,
                }
        except SimulationCheckFailed as error:
            return StepOutcome.failed(SIMULATION_CHECK_FAILED, str(error))
        except Exception as error:
            logger.exception("The traveller simulation of run %s failed", run.id)
            return StepOutcome.failed(STAGE_ERROR, f"{type(error).__name__}: {error}")
        if stop.is_set():
            # A cancelled simulation writes nothing.
            return StepOutcome.stopped_on_signal()
        try:
            self._simulations.store(new, self._links(context))
        except Exception as error:
            logger.exception("The storing of the simulations of run %s failed", run.id)
            return StepOutcome.failed(STAGE_ERROR, f"{type(error).__name__}: {error}")
        return StepOutcome.done(counts)

    def _scheme(self, name: str, context: _Context) -> PriceScheme:
        goals = context.version.goals
        fare, parking = float(goals.pt_fare_chf), float(goals.car_parking_fee_chf)
        if name == "model_prices":
            return ModelPrices(
                model_bike_prices(self._solves.rows(context.solve_key)), fare, parking
            )
        return FlatPrice(float(goals.flat_price_per_ride_chf), fare, parking)

    def _links(self, context: _Context) -> list[SimulationLink]:
        now = self._clock.now()
        return [
            SimulationLink(
                context.version.id,
                context.period_id,
                name,
                context.rule.rule_id,
                context.rule.rule_version,
                context.keys[name],
                now,
            )
            for name in SCHEMES
        ]

    def _context(self, run: Run, step: RunStep) -> _Context | str:
        """The keys of the two simulations, or the reason there are none."""
        rule = self._rule()
        version = self._pricing_versions.get(run.subject.id)
        if version is None:
            raise PricingVersionNotFound(run.subject.id)
        period_id = step.period or self._pricing_versions.period_ids(version.id)[0]
        instance_key = self._artifacts.links_of(version.instance_version_id).get(
            StepName.TRAVELLERS_AND_BIKES
        )
        if instance_key is None:
            return NO_INSTANCE_REASON
        solve_key = self._solves.solve_key_of(version.id, period_id)
        if solve_key is None:
            return NO_SOLVE_REASON
        goals = version.goals
        common: dict[str, Any] = {
            "instance_key": instance_key,
            "period_id": period_id,
            "rule_id": rule.rule_id,
            "rule_version": rule.rule_version,
            "rule_parameters": rule.parameters,
            "pt_fare_chf": float(goals.pt_fare_chf),
            "car_parking_fee_chf": float(goals.car_parking_fee_chf),
        }
        keys = {
            "model_prices": simulation_key(
                **common,
                scheme_kind="model_prices",
                solve_key=solve_key,
                flat_price_kind=None,
                flat_price_amount_chf=None,
            ),
            "flat": simulation_key(
                **common,
                scheme_kind="flat",
                solve_key=None,
                flat_price_kind=goals.flat_price_kind,
                flat_price_amount_chf=float(goals.flat_price_per_ride_chf),
            ),
        }
        return _Context(rule, version, period_id, instance_key, solve_key, keys)
