from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from pricing_demo.domain.system_status import ComponentName, ComponentStatus

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class StorageProbe:
    """The database answers and has every migration applied."""

    component = ComponentName.STORAGE

    def __init__(self, engine: Engine) -> None:
        config = Config()
        config.set_main_option("script_location", str(MIGRATIONS_DIR))
        self._engine = engine
        self._head = ScriptDirectory.from_config(config).get_current_head()

    def check(self) -> ComponentStatus:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                current = MigrationContext.configure(connection).get_current_revision()
        except Exception as error:
            return ComponentStatus.unavailable(
                self.component, f"The database does not answer: {_first_line(error)}"
            )
        if current != self._head:
            return ComponentStatus.unavailable(
                self.component,
                f"The database is at migration {current or 'none'}, the API needs {self._head}.",
            )
        return ComponentStatus.ready(self.component)


def _first_line(error: Exception) -> str:
    detail = getattr(error, "orig", None) or error
    lines = [line.strip() for line in str(detail).splitlines() if line.strip()]
    return lines[0] if lines else type(error).__name__
