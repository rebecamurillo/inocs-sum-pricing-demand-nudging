import threading
from collections.abc import Collection, Sequence

from pricing_demo.application.ports.simulations import (
    LinkedSimulation,
    SimulationLink,
    StoredSimulation,
)


def _slot(link: SimulationLink) -> tuple[str, str, str, str, int]:
    return (
        link.pricing_version_id,
        link.period_id,
        link.price_scheme,
        link.rule_id,
        link.rule_version,
    )


class InMemorySimulations:
    """The simulations and the links in dicts; passes the same contract suite as the
    PostgreSQL adapter. One lock guards both: the worker's executor runs in a thread of its
    own."""

    def __init__(self) -> None:
        self._simulations: dict[str, StoredSimulation] = {}
        self._links: dict[tuple[str, str, str, str, int], SimulationLink] = {}
        self._lock = threading.Lock()

    def is_stored(self, key: str) -> bool:
        with self._lock:
            return key in self._simulations

    def store(self, new: Sequence[StoredSimulation], links: Sequence[SimulationLink]) -> None:
        with self._lock:
            known = {*self._simulations, *(item.key for item in new)}
            missing = [link.simulation_key for link in links if link.simulation_key not in known]
            if missing:
                raise KeyError(missing[0])
            for simulation in new:
                self._simulations.setdefault(simulation.key, simulation)
            for link in links:
                self._links[_slot(link)] = link

    def links_of(self, pricing_version_id: str) -> list[SimulationLink]:
        with self._lock:
            found = [
                item
                for item in self._links.values()
                if item.pricing_version_id == pricing_version_id
            ]
        return sorted(
            found,
            key=lambda item: (item.period_id, item.price_scheme, item.rule_id, item.rule_version),
        )

    def linked_of(self, pricing_version_id: str) -> list[LinkedSimulation]:
        found = self.links_of(pricing_version_id)
        with self._lock:
            return [
                LinkedSimulation(
                    item.pricing_version_id,
                    item.period_id,
                    item.price_scheme,
                    item.rule_id,
                    item.rule_version,
                    dict(self._simulations[item.simulation_key].outputs.parameters),
                    item.simulation_key,
                    item.created_at,
                )
                for item in found
            ]

    def remove_unlinked(self) -> int:
        with self._lock:
            linked = {item.simulation_key for item in self._links.values()}
            unlinked = [key for key in self._simulations if key not in linked]
            for key in unlinked:
                del self._simulations[key]
            return len(unlinked)

    # What a test reads and what the deletion of a version does; the port has no such methods.
    def get(self, key: str) -> StoredSimulation | None:
        with self._lock:
            return self._simulations.get(key)

    def drop_version(self, version_ids: Collection[str]) -> None:
        with self._lock:
            for slot in [item for item in self._links if item[0] in version_ids]:
                del self._links[slot]
