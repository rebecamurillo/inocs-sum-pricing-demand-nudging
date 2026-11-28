from collections.abc import Callable
from dataclasses import dataclass

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.city_datasets import CityDatasets
from pricing_demo.application.ports.city_instances import CityInstances
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.showcase import Showcase, ShowcaseMark
from pricing_demo.application.ports.simulations import Simulations
from pricing_demo.application.ports.solves import Solves
from pricing_demo.application.result_lookup import FoundResult, ResultLookup
from pricing_demo.application.use_cases.get_pricing_result import _runs_under, headline_numbers
from pricing_demo.domain.city_datasets import city_name
from pricing_demo.domain.derived_result import (
    SimulationSummary,
    derived_pair_bike_rides,
    offered_rides,
)
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import NoShowcase, ResultNotFound
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.system_status import SystemStatus

CAR_SHARE_UNIT = "points"


@dataclass(frozen=True)
class ShowcasePoint:
    lat: Number
    lon: Number


@dataclass(frozen=True)
class ShowcaseHub:
    hub_id: str
    centre: ShowcasePoint
    outline: dict[str, object] | None


@dataclass(frozen=True)
class ShowcasePair:
    """A hub pair with bike rides: its two hub centres, the ride-weighted mean bike price and
    the bike rides, both computed from the model's flows."""

    origin_hub: str
    destination_hub: str
    origin: ShowcasePoint
    destination: ShowcasePoint
    mean_bike_price: Number
    bike_rides: Number


@dataclass(frozen=True)
class ShowcaseView:
    mark: ShowcaseMark
    letter: str
    instance_version_id: str
    instance_version_name: str
    headline: dict[str, Number]
    dataset_id: str
    city: str
    radius_km: Number
    period_label: str
    car_share_flat: Number
    car_share_version: Number
    car_share_difference: Number
    flat_price: Number
    rule_id: str
    rule_version: int
    rule_current: bool
    circle_centre: ShowcasePoint
    circle_radius_m: Number
    hubs: list[ShowcaseHub]
    hub_pairs: list[ShowcasePair]


def _point(lat: float, lon: float) -> ShowcasePoint:
    return ShowcasePoint(
        Number(lat, "degrees", "input", "headline"), Number(lon, "degrees", "input", "headline")
    )


def _car_share(summary: SimulationSummary) -> float:
    if not summary.travellers:
        return 0.0
    return 100.0 * summary.travellers_per_mode.get("car", 0) / summary.travellers


class GetShowcase:
    """The showcased pricing version with what Home draws: its instance version's name, its
    letter, the headline numbers of its result, the car shares simulated with the flat price and
    with the version's prices, the study circle, the hubs and the hub pairs with bike rides.
    Raises `NoShowcase` when none is marked, and `ResultNotFound` when the marked version has
    lost a part of its result."""

    def __init__(
        self,
        showcase: Showcase,
        lookup: ResultLookup,
        instances: CityInstances,
        simulations: Simulations,
        datasets: CityDatasets,
        artifacts: Artifacts,
        read_model: ReadModel,
        solves: Solves,
        system_status: Callable[[], SystemStatus],
    ) -> None:
        self._showcase = showcase
        self._lookup = lookup
        self._instances = instances
        self._simulations = simulations
        self._datasets = datasets
        self._artifacts = artifacts
        self._read_model = read_model
        self._solves = solves
        self._system_status = system_status

    def execute(self) -> ShowcaseView:
        mark = self._showcase.current()
        if mark is None:
            raise NoShowcase()
        found = self._lookup.find(mark.pricing_version_id, mark.period_id)
        version = found.version
        instance_version = self._instances.get_version(version.instance_version_id)
        instance = (
            None
            if instance_version is None
            else self._instances.get_instance(instance_version.instance_id)
        )
        if instance_version is None or instance is None:
            raise ResultNotFound(version.id)
        dataset = self._datasets.get(instance.dataset_id)
        period = next(
            (
                item
                for item in self._instances.periods_of(version.instance_version_id)
                if item.id == found.period_id
            ),
            None,
        )
        links = self._artifacts.links_of(version.instance_version_id)
        hubs_key = links.get(StepName.HUBS)
        instance_key = links.get(StepName.TRAVELLERS_AND_BIKES)
        if period is None or hubs_key is None or instance_key is None:
            raise ResultNotFound(version.id)
        flat, with_model = self._summaries(found)
        parameters = instance_version.parameters
        hubs = self._read_model.hubs(hubs_key)
        centres = {hub.hub_id: _point(hub.lat, hub.lon) for hub in hubs}
        rides = offered_rides(
            self._solves.rows(found.solve.key), self._read_model.route_options(instance_key)
        )
        pairs = [
            ShowcasePair(
                origin,
                destination,
                centres[origin],
                centres[destination],
                Number(mean, "chf_per_bike_leg", "derived", "headline"),
                Number(total, "bike_rides", "derived", "headline"),
            )
            for (origin, destination), (total, mean) in sorted(
                derived_pair_bike_rides(rides).items()
            )
            if mean is not None and origin in centres and destination in centres
        ]
        link = found.links["model_prices"]
        rule = self._system_status().simulation_rule
        flat_share, version_share = _car_share(flat), _car_share(with_model)
        return ShowcaseView(
            mark,
            version.letter,
            version.instance_version_id,
            f"{instance.name} v{instance_version.number}",
            headline_numbers(found.summary.numbers),
            instance.dataset_id,
            city_name(instance.name if dataset is None else dataset.name),
            Number(parameters.radius_m / 1000, "km", "input", "headline"),
            period.label,
            Number(flat_share, CAR_SHARE_UNIT, "simulation", "headline"),
            Number(version_share, CAR_SHARE_UNIT, "simulation", "headline"),
            Number(flat_share - version_share, CAR_SHARE_UNIT, "simulation", "headline"),
            Number(version.goals.flat_price_per_ride_chf, "chf_per_ride", "input", "headline"),
            link.rule_id,
            link.rule_version,
            rule is not None and _runs_under(link, with_model, rule),
            _point(parameters.center_lat, parameters.center_lon),
            Number(parameters.radius_m, "m", "input", "headline"),
            [
                ShowcaseHub(
                    hub.hub_id, centres[hub.hub_id], dict(hub.outline) if hub.outline else None
                )
                for hub in hubs
            ],
            pairs,
        )

    def _summaries(self, found: FoundResult) -> tuple[SimulationSummary, SimulationSummary]:
        found_summaries = []
        for scheme in ("flat", "model_prices"):
            link = found.links[scheme]
            summary = self._simulations.summary_of(link.simulation_key)
            if summary is None:
                raise ResultNotFound(found.version.id)
            found_summaries.append(summary)
        return found_summaries[0], found_summaries[1]
