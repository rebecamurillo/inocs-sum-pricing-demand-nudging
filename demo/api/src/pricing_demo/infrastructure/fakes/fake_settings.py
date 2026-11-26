from collections.abc import Mapping

from pricing_demo.domain.system_status import PROBED_COMPONENTS


def default_settings() -> dict[str, object]:
    return {
        "components": {
            name.value: {"state": "available", "reason": None} for name in PROBED_COMPONENTS
        }
    }


class InMemoryFakeSettings:
    """The `fake_settings` row in a dict; passes the same contract suite as the PostgreSQL one."""

    def __init__(self) -> None:
        self._settings: dict[str, object] = {}

    def read(self) -> Mapping[str, object]:
        return self._settings

    def set_component(self, name: str, state: str, reason: str | None) -> None:
        components = dict(self._settings.get("components") or {})  # type: ignore[call-overload]
        components[name] = {"state": state, "reason": reason}
        self._settings = {**self._settings, "components": components}

    def write_defaults(self) -> None:
        self._settings = default_settings()
