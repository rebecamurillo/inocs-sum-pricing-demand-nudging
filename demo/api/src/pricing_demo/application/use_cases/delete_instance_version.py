from pricing_demo.application.ports.builds import Builds


class DeleteInstanceVersion:
    """Deletes a draft or a saved version with its runs, and its instance when it was the only
    version. Refused (`RunActive`) while a run of it is queued or running."""

    def __init__(self, builds: Builds) -> None:
        self._builds = builds

    def execute(self, version_id: str) -> None:
        self._builds.delete_version(version_id)
