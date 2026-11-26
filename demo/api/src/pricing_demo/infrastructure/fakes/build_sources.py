from collections.abc import Mapping


class InMemoryBuildSources:
    """The package fingerprint and the graph manifest, as the test sets them."""

    def __init__(
        self, fingerprint: str | None = None, manifest: Mapping[str, object] | None = None
    ) -> None:
        self.fingerprint = fingerprint
        self.manifest = manifest

    def package_fingerprint(self) -> str | None:
        return self.fingerprint

    def graph_manifest(self) -> Mapping[str, object] | None:
        return self.manifest
