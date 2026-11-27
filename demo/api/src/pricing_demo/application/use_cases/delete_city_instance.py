from pricing_demo.application.ports.builds import Builds


class DeleteCityInstance:
    """Deletes an instance with every version and run below it. Refused (`RunActive`) while a
    run of any version is queued or running, and (`HasPricingVersions`)
    while it has pricing versions, unless they are included."""

    def __init__(self, builds: Builds) -> None:
        self._builds = builds

    def execute(self, instance_id: str, including_pricing_versions: bool = False) -> None:
        self._builds.delete_instance(instance_id, including_pricing_versions)
