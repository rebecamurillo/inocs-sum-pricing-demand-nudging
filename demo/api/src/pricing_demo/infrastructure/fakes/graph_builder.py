from pathlib import Path

from pricing_demo.application.errors import GraphBuildFailed


class FakeGraphBuilder:
    """Stands in for the OpenTripPlanner build: records what the folder held, leaves a graph."""

    def __init__(
        self, fail_with: str | None = None, image: str = "fake-otp", folder: Path | None = None
    ) -> None:
        self._fail_with = fail_with
        self._image = image
        self._folder = folder
        # The sorted file names the folder held at each `build()`.
        self.calls: list[list[str]] = []

    @property
    def image(self) -> str:
        return self._image

    def build(self) -> None:
        if self._folder is not None:
            self.calls.append(sorted(path.name for path in self._folder.iterdir()))
        else:
            self.calls.append([])
        if self._fail_with is not None:
            raise GraphBuildFailed(self._fail_with)
        if self._folder is not None:
            (self._folder / "graph.obj").write_bytes(b"fake graph")
