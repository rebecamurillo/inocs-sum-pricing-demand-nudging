from pricing_demo.application.ports.builds import Builds


class DeleteCityInstance:
    """Deletes an instance with every version and run below it. Refused (`RunActive`) while a
    run of any version is queued or running."""

    def __init__(self, builds: Builds) -> None:
        self._builds = builds

    def execute(self, instance_id: str) -> None:
        self._builds.delete_instance(instance_id)
