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

    def set_pricing_model(self, value: Mapping[str, object] | None) -> None:
        """Set what the fake pricing model does (`fail_at`, `hold_at`, `routes_pace_ms`); None
        returns it to its defaults: no failure, no hold, no pace."""
        settings = {key: item for key, item in self._settings.items() if key != "pricing_model"}
        if value is not None:
            settings["pricing_model"] = dict(value)
        self._settings = settings

    def release_run(self, run_id: str) -> None:
        released = list(self._settings.get("released_runs") or [])  # type: ignore[call-overload]
        if run_id not in released:
            released.append(run_id)
        self._settings = {**self._settings, "released_runs": released}

    def write_defaults(self) -> None:
        self._settings = default_settings()
