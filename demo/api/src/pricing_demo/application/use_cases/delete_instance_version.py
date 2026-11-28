from pricing_demo.application.ports.builds import Builds
from pricing_demo.application.ports.showcase import Showcase
from pricing_demo.domain.pricing_versions import IsShowcase, instance_version_of


class DeleteInstanceVersion:
    """Deletes a draft or a saved version with its runs, and its instance when it was the only
    version. Refused first (`IsShowcase`) while a pricing version of it is the home page's
    showcase, then (`RunActive`) while a run of it is queued or running, and
    (`HasPricingVersions`) while it has pricing versions, unless they are included."""

    def __init__(self, builds: Builds, showcase: Showcase) -> None:
        self._builds = builds
        self._showcase = showcase

    def execute(self, version_id: str, including_pricing_versions: bool = False) -> None:
        mark = self._showcase.current()
        if mark is not None and instance_version_of(mark.pricing_version_id) == version_id:
            raise IsShowcase(mark.pricing_version_id)
        self._builds.delete_version(version_id, including_pricing_versions)
