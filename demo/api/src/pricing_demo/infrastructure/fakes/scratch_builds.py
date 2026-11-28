from pathlib import Path

from pricing_demo.infrastructure.artifact_store.scratch import LocalScratchBuilds


class FakeScratchBuilds(LocalScratchBuilds):
    """Scratch folders under a test's own root; records the roots it was asked to remove."""

    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self.removed: list[Path] = []

    def remove(self, root: Path) -> None:
        self.removed.append(root)
        super().remove(root)
