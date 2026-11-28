from dataclasses import dataclass

from pricing_demo.application.ports.artifacts import Artifacts
from pricing_demo.application.ports.read_model import ReadModel
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.domain.derived_result import HubNumbers
from pricing_demo.domain.pricing_versions import ResultNotFound
from pricing_demo.domain.read_model import HubRow
from pricing_demo.domain.runs import StepName


@dataclass(frozen=True)
class HubResult:
    hub: HubRow
    numbers: HubNumbers


class ListHubResults:
    """Per hub: the bike rides that start and end there and the mean bike price from it."""

    def __init__(self, lookup: ResultLookup, artifacts: Artifacts, read_model: ReadModel) -> None:
        self._lookup = lookup
        self._artifacts = artifacts
        self._read_model = read_model

    def execute(self, version_id: str, period_id: str | None = None) -> list[HubResult]:
        found = self._lookup.find(version_id, period_id)
        hubs_key = self._artifacts.links_of(found.version.instance_version_id).get(StepName.HUBS)
        if hubs_key is None:
            raise ResultNotFound(version_id)
        hubs = {hub.hub_id: hub for hub in self._read_model.hubs(hubs_key)}
        return [
            HubResult(hubs[item.hub_id], item)
            for item in found.summary.numbers.hubs
            if item.hub_id in hubs
        ]
