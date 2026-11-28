from importlib.metadata import PackageNotFoundError, version

from pricing_demo.domain.system_status import ComponentName, ComponentStatus

PACKAGE = "sum_nsm_dynamic_pricing"


class PackageProbe:
    """The research package is installed and imports."""

    component = ComponentName.PACKAGE

    def check(self) -> ComponentStatus:
        try:
            installed = version(PACKAGE)
        except PackageNotFoundError:
            return ComponentStatus.unavailable(self.component, f"{PACKAGE} is not installed.")
        try:
            import sum_nsm_dynamic_pricing  # noqa: F401
        except Exception as error:
            return ComponentStatus.unavailable(
                self.component,
                f"{PACKAGE} {installed} does not import: {type(error).__name__}: {error}",
            )
        return ComponentStatus.ready(self.component)
