from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.showcase import Showcase
from pricing_demo.domain.pricing_versions import IsShowcase, city_instance_of, instance_version_of


class DeleteCityInstance:
    """Deletes an instance with every version and run below it. Refused first (`IsShowcase`)
    while a pricing version below it is the home page's showcase, then (`RunActive`) while a
    run of any version is queued or running, and (`HasPricingVersions`)
    while it has pricing versions, unless they are included."""

    def __init__(self, builds: Builds, showcase: Showcase) -> None:
        self._builds = builds
        self._showcase = showcase

    def execute(self, instance_id: str, including_pricing_versions: bool = False) -> None:
        mark = self._showcase.current()
        if mark is not None:
            held = city_instance_of(instance_version_of(mark.pricing_version_id))
            if held == instance_id:
                raise IsShowcase(mark.pricing_version_id)
        self._builds.delete_instance(instance_id, including_pricing_versions)
