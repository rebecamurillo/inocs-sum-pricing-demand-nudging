from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert

from pricing_demo.infrastructure.fakes.fake_settings import default_settings
from pricing_demo.infrastructure.persistence.tables import fake_settings


class PostgresFakeSettings:
    """The one `fake_settings` row. Built only by the composition roots' fake branch."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read(self) -> Mapping[str, object]:
        with self._engine.connect() as connection:
            row = connection.execute(select(fake_settings.c.settings)).scalar()
        return row or {}

    def set_component(self, name: str, state: str, reason: str | None) -> None:
        current: dict[str, Any] = dict(self.read())
        components = dict(current.get("components") or {})
        components[name] = {"state": state, "reason": reason}
        self._write({**current, "components": components})

    def set_pricing_model(self, value: Mapping[str, object] | None) -> None:
        current = {key: item for key, item in self.read().items() if key != "pricing_model"}
        if value is not None:
            current["pricing_model"] = dict(value)
        self._write(current)

    def release_run(self, run_id: str) -> None:
        current: dict[str, Any] = dict(self.read())
        released = list(current.get("released_runs") or [])
        if run_id not in released:
            released.append(run_id)
        self._write({**current, "released_runs": released})

    def write_defaults(self) -> None:
        self._write(default_settings())

    def _write(self, settings: Mapping[str, object]) -> None:
        statement = insert(fake_settings).values(id=1, settings=dict(settings))
        statement = statement.on_conflict_do_update(
            index_elements=["id"], set_={"settings": statement.excluded.settings}
        )
        with self._engine.begin() as connection:
            connection.execute(statement)
