from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.package_fingerprints import PackageFingerprints
from pricing_demo.application.ports.simulations import (
    LinkedSimulation,
    SimulationLink,
    Simulations,
)
from pricing_demo.application.result_lookup import SCHEMES, FoundResult, ResultLookup
from pricing_demo.application.use_cases.simulate_pricing_version import has_rule
from pricing_demo.domain.derived_result import (
    GOAL_ORDER,
    HEADLINE_NUMBERS,
    MODEL_GOAL_NUMBERS,
    SPLIT_NUMBERS,
    ResultNumbers,
    SimulationSummary,
    parameter_numbers,
    simulated_goals,
)
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.package_fingerprint import CHOICE_COEFFICIENT_NAMES
from pricing_demo.domain.pricing_keys import PACKAGE_GOAL_NAMES
from pricing_demo.domain.pricing_versions import PricingVersion
from pricing_demo.domain.system_status import SystemStatus
from pricing_demo.domain.traveller_simulation import SimulationRule


@dataclass(frozen=True)
class SimulationResult:
    """The latest simulation of a scheme with its rule and its goals."""

    link: SimulationLink
    summary: SimulationSummary
    rule_current: bool
    goals: dict[str, Number]


@dataclass(frozen=True)
class StoredSimulationFigures:
    """One stored simulation of the version: the figures stories 3-9 to 3-12 read."""

    link: SimulationLink
    bike_rides: Number
    revenue: Number
    cost: Number


@dataclass(frozen=True)
class GoalComparison:
    """A goal with the model's own value (absent when it has none) and both simulated values."""

    name: str
    model: Number | None
    model_prices: Number | None
    flat: Number | None
    change: Number | None


@dataclass(frozen=True)
class SimulationProvenance:
    """The rule and the date of the latest simulation of a scheme."""

    price_scheme: str
    rule_id: str
    rule_version: int
    created_at: datetime


@dataclass(frozen=True)
class Provenance:
    run_id: str
    solve_key: str
    derivation_version: int
    package_fingerprint: str
    package_version: str | None
    package_commit: str | None
    package_dirty: bool | None
    gurobi_version: str
    licence_kind: str
    solver_parameters: dict[str, object]
    dependency_lock_sha256: str
    platform: str
    demonstrator_version: str
    input_keys: dict[str, str]
    gtfs_sha256: str | None
    gbfs_sha256: str | None
    timetable_valid_from: date | None
    timetable_valid_to: date | None
    routing_date: date | None
    routing_time: time | None
    routing_date_provisional: bool | None
    bike_stations_fetched_at: datetime | None
    timetable_operator: str | None
    bike_stations_source_url: str | None
    simulations: list[SimulationProvenance]


@dataclass(frozen=True)
class PricingResult:
    version: PricingVersion
    period_id: str
    numbers: ResultNumbers
    headline: dict[str, Number]
    model_split: dict[str, Number]
    goals: list[GoalComparison]
    simulations: list[SimulationResult]
    simulation_history: list[StoredSimulationFigures]
    advanced: dict[str, Number]
    solver_status_name: str
    coefficients: dict[str, Number | None] | None
    provenance: Provenance


def headline_numbers(numbers: ResultNumbers) -> dict[str, Number]:
    return {name: numbers.numbers[name] for name in HEADLINE_NUMBERS if name in numbers.numbers}


class GetPricingResult:
    """The numbers of a finished version, each with its source (AR-20)."""

    def __init__(
        self,
        lookup: ResultLookup,
        simulations: Simulations,
        instances: CityInstances,
        datasets: CityDatasets,
        artifacts: Artifacts,
        fingerprints: PackageFingerprints,
        system_status: Callable[[], SystemStatus],
    ) -> None:
        self._lookup = lookup
        self._simulations = simulations
        self._instances = instances
        self._datasets = datasets
        self._artifacts = artifacts
        self._fingerprints = fingerprints
        self._system_status = system_status

    def execute(self, version_id: str, period_id: str | None = None) -> PricingResult:
        found = self._lookup.find(version_id, period_id)
        numbers = found.summary.numbers
        version = found.version
        simulations = self._simulation_results(found)
        advanced = self._advanced(found)
        return PricingResult(
            version,
            found.period_id,
            numbers,
            headline_numbers(numbers),
            {name: numbers.numbers[name] for name in SPLIT_NUMBERS if name in numbers.numbers},
            self._goals(numbers, simulations),
            simulations,
            self._history(version, float(version.goals.cost_bike_chf)),
            advanced,
            found.solve.quality.solver_status_name,
            self._coefficients(found.solve.provenance.package_fingerprint),
            self._provenance(found, simulations),
        )

    def _simulation_results(self, found: FoundResult) -> list[SimulationResult]:
        rule = self._system_status().simulation_rule
        cost_bike = float(found.version.goals.cost_bike_chf)
        results = []
        for scheme in SCHEMES:
            link = found.links[scheme]
            summary = self._simulations.summary_of(link.simulation_key)
            if summary is None:
                raise LookupError(f"the simulation {link.simulation_key} is linked and not stored")
            results.append(
                SimulationResult(
                    link,
                    summary,
                    rule is not None and _runs_under(link, summary, rule),
                    simulated_goals(summary, cost_bike),
                )
            )
        return results

    @staticmethod
    def _goals(numbers: ResultNumbers, simulations: list[SimulationResult]) -> list[GoalComparison]:
        by_scheme = {item.link.price_scheme: item.goals for item in simulations}
        found = []
        for name in GOAL_ORDER:
            model = numbers.numbers.get(MODEL_GOAL_NUMBERS[name])
            with_model = by_scheme["model_prices"].get(name)
            flat = by_scheme["flat"].get(name)
            change = None
            if with_model is not None and flat is not None:
                change = Number(
                    with_model.value - flat.value, with_model.unit, "simulation", "headline"
                )
            found.append(GoalComparison(name, model, with_model, flat, change))
        return found

    def _history(self, version: PricingVersion, cost_bike: float) -> list[StoredSimulationFigures]:
        history = []
        for link in self._simulations.links_of(version.id):
            summary = self._simulations.summary_of(link.simulation_key)
            if summary is None:
                continue
            goals = simulated_goals(summary, cost_bike)
            history.append(
                StoredSimulationFigures(
                    link,
                    Number(summary.bike_rides, "bike_rides", "simulation", "headline"),
                    goals["revenue"],
                    goals["cost"],
                )
            )
        return history

    def _advanced(self, found: FoundResult) -> dict[str, Number]:
        quality = found.solve.quality
        numbers = found.summary.numbers
        advanced: dict[str, Number] = {}

        def add(name: str, value: float | int | None, unit: str, source: str = "model") -> None:
            if value is not None:
                advanced[name] = Number(value, unit, source, "advanced")  # type: ignore[arg-type]

        add("solver_status", quality.solver_status, "status")
        add("objective_value", quality.objective_value, "objective")
        add("gap_pct", quality.gap_pct, "percent")
        add("solution_time_s", quality.solution_time_s, "seconds")
        add("solution_count", quality.sol_count, "solutions")
        add("time_limit_reached", int(quality.time_limit_reached), "flag")
        if numbers.objective_terms is not None:
            for name, term in numbers.objective_terms.items():
                advanced[f"objective_term_{name}"] = term
        add("objective_residual", numbers.objective_residual, "ratio", "derived")
        package = found.summary.package_summary or {}
        for name, key in (
            ("package_avg_bike_price_multimodal", "Avg Bike Price (Multimodal, Flow ≥ 1)"),
            ("package_avg_bike_price_offered", "Avg Bike Price (for all offered arcs)"),
        ):
            value = package.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool):
                add(name, value, "chf_per_bike_leg", "package_summary")
        for name, item in parameter_numbers(
            found.version.goals.as_dict(), PACKAGE_GOAL_NAMES
        ).items():
            advanced[f"parameter_{name}"] = item
        return advanced

    def _coefficients(self, fingerprint: str) -> dict[str, Number | None] | None:
        stored = self._fingerprints.get(fingerprint)
        if stored is None:
            return None
        found: dict[str, Number | None] = {}
        for name in CHOICE_COEFFICIENT_NAMES:
            value = stored.choice_coefficients.get(name)
            found[name] = (
                None if value is None else Number(value, "coefficient", "input", "advanced")
            )
        return found

    def _provenance(self, found: FoundResult, simulations: list[SimulationResult]) -> Provenance:
        version = found.version
        solve = found.solve
        stored = self._fingerprints.get(solve.provenance.package_fingerprint)
        instance_version = self._instances.get_version(version.instance_version_id)
        instance = (
            None
            if instance_version is None
            else self._instances.get_instance(instance_version.instance_id)
        )
        dataset = None if instance is None else self._datasets.get(instance.dataset_id)
        period = next(
            (
                item
                for item in self._instances.periods_of(version.instance_version_id)
                if item.id == found.period_id
            ),
            None,
        )
        return Provenance(
            run_id=found.run.id,
            solve_key=solve.key,
            derivation_version=found.summary.derivation_version,
            package_fingerprint=solve.provenance.package_fingerprint,
            package_version=None if stored is None else stored.version,
            package_commit=None if stored is None else stored.git_commit,
            package_dirty=None if stored is None else stored.git_dirty,
            gurobi_version=solve.provenance.gurobi_version,
            licence_kind=solve.provenance.licence_kind,
            solver_parameters=dict(solve.provenance.solver_parameters),
            dependency_lock_sha256=solve.provenance.dependency_lock_sha256,
            platform=solve.provenance.platform,
            demonstrator_version=solve.provenance.demonstrator_version,
            input_keys={
                step.value: key
                for step, key in self._artifacts.links_of(version.instance_version_id).items()
            },
            gtfs_sha256=None if dataset is None else dataset.gtfs.sha256,
            gbfs_sha256=None if dataset is None else dataset.gbfs.sha256,
            timetable_valid_from=None if dataset is None else dataset.gtfs.valid_from,
            timetable_valid_to=None if dataset is None else dataset.gtfs.valid_to,
            routing_date=None if period is None else period.routing_date,
            routing_time=None if period is None else period.routing_time,
            routing_date_provisional=None if period is None else period.routing_date_provisional,
            bike_stations_fetched_at=None if dataset is None else dataset.gbfs.fetched_at,
            timetable_operator=None if dataset is None else dataset.gtfs.operator,
            bike_stations_source_url=None if dataset is None else dataset.gbfs.source_url,
            simulations=[
                SimulationProvenance(
                    item.link.price_scheme,
                    item.link.rule_id,
                    item.link.rule_version,
                    item.link.created_at,
                )
                for item in simulations
            ],
        )


def _runs_under(link: SimulationLink, summary: SimulationSummary, rule: SimulationRule) -> bool:
    return has_rule(
        LinkedSimulation(
            link.pricing_version_id,
            link.period_id,
            link.price_scheme,
            link.rule_id,
            link.rule_version,
            summary.rule_parameters,
            link.simulation_key,
            link.created_at,
        ),
        rule,
    )
