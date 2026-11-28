from dataclasses import dataclass

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.ports.solves import Solves
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.domain.derived_result import PairNumbers
from pricing_demo.domain.numbers import Number
from pricing_demo.domain.pricing_versions import ResultNotFound
from pricing_demo.domain.read_model import RouteLeg, RouteMode
from pricing_demo.domain.runs import StepName


@dataclass(frozen=True)
class OptionResult:
    """An option of a hub pair: its route from step 3, and what the model made of it. An
    option the model does not offer has no price and no riders."""

    arc_id: str
    mode: RouteMode
    legs: tuple[RouteLeg, ...]
    duration_s: Number
    bike_legs: Number | None
    bike_price: Number | None
    riders: Number | None


@dataclass(frozen=True)
class HubPairResult:
    numbers: PairNumbers
    options: tuple[OptionResult, ...]


class ListHubPairResults:
    """Per hub pair of the instance: the bike price (mean, lowest, highest), the travellers
    per mode and the options with their routes, prices and riders."""

    def __init__(
        self,
        lookup: ResultLookup,
        solves: Solves,
        artifacts: Artifacts,
        read_model: ReadModel,
    ) -> None:
        self._lookup = lookup
        self._solves = solves
        self._artifacts = artifacts
        self._read_model = read_model

    def execute(self, version_id: str, period_id: str | None = None) -> list[HubPairResult]:
        found = self._lookup.find(version_id, period_id)
        instance_key = self._artifacts.links_of(found.version.instance_version_id).get(
            StepName.TRAVELLERS_AND_BIKES
        )
        if instance_key is None:
            raise ResultNotFound(version_id)
        rows = {row.arc_id: row for row in self._solves.rows(found.solve.key)}
        by_pair: dict[tuple[str, str], list[OptionResult]] = {}
        for option in self._read_model.route_options(instance_key):
            row = rows.get(option.arc_id)
            by_pair.setdefault((option.origin_hub, option.destination_hub), []).append(
                OptionResult(
                    option.arc_id,
                    option.mode,
                    option.legs,
                    Number(
                        option.total_travel_time_s + option.total_transfer_time_s,
                        "seconds",
                        "trip_planner",
                        "headline",
                    ),
                    None
                    if option.bike_legs is None
                    else Number(option.bike_legs, "bike_legs", "input", "headline"),
                    None
                    if row is None or row.bike_price is None
                    else Number(row.bike_price, "chf_per_bike_leg", "model", "headline"),
                    None if row is None else Number(row.flow, "travellers", "model", "headline"),
                )
            )
        return [
            HubPairResult(pair, tuple(by_pair.get((pair.origin_hub, pair.destination_hub), ())))
            for pair in found.summary.numbers.pairs
        ]
