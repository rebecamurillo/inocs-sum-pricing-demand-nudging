from collections.abc import Callable, Mapping

from pricing_demo.application.ports.trip_planner_graph import GraphFingerprints


class WorkerBuildSources:
    """What the worker itself knows: the fingerprint of the package it runs and the manifest
    of the graph in its folder."""

    def __init__(
        self, package_fingerprint: Callable[[], str | None], graph: GraphFingerprints
    ) -> None:
        self._package_fingerprint = package_fingerprint
        self._graph = graph

    def package_fingerprint(self) -> str | None:
        return self._package_fingerprint()

    def graph_manifest(self) -> Mapping[str, object] | None:
        return self._graph.read().manifest
