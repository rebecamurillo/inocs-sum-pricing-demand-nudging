from collections.abc import Mapping
from typing import Protocol


class BuildSources(Protocol):
    """What a plan needs that no instance holds: the pricing package's fingerprint and the
    trip planner's graph manifest. None when not known yet."""

    def package_fingerprint(self) -> str | None: ...

    def graph_manifest(self) -> Mapping[str, object] | None: ...
