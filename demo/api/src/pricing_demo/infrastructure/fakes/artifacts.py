import threading
from collections.abc import Collection, Mapping

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.domain.runs import StepName


class InMemoryArtifacts:
    """The artefacts and the links in dicts; passes the same contract suite as PostgreSQL.

    One lock guards both: the worker's executor runs in a thread of its own.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, Artifact] = {}
        self._links: dict[tuple[str, StepName, str | None], str] = {}
        self._lock = threading.Lock()

    def stored_keys(self, keys: Collection[str]) -> set[str]:
        with self._lock:
            return {key for key in keys if key in self._artifacts}

    def get(self, key: str) -> Artifact | None:
        with self._lock:
            return self._artifacts.get(key)

    def add(self, artifact: Artifact) -> None:
        with self._lock:
            self._artifacts.setdefault(artifact.input_key, artifact)

    def link(self, version_id: str, step: StepName, period_id: str | None, key: str) -> None:
        with self._lock:
            if key not in self._artifacts:
                raise KeyError(key)
            self._links[(version_id, step, period_id)] = key

    def links_of(self, version_id: str) -> Mapping[StepName, str]:
        with self._lock:
            return {
                step: key
                for (version, step, _), key in self._links.items()
                if version == version_id
            }

    def clear(self) -> None:
        with self._lock:
            self._artifacts.clear()
            self._links.clear()
