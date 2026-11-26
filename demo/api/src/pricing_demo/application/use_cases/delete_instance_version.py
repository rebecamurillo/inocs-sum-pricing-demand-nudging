from pricing_demo.application.ports.city_instances import CityInstances


class DeleteInstanceVersion:
    """Discards a draft, and its instance when the draft was the only version."""

    def __init__(self, instances: CityInstances) -> None:
        self._instances = instances

    def execute(self, version_id: str) -> None:
        self._instances.delete_draft(version_id)
