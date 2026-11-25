"""Write the OpenAPI document: `python -m pricing_demo.export_openapi <path>`.

Builds the application with the fake adapters, so it needs no database, solver or trip planner.
"""

import json
import sys
from pathlib import Path

from pricing_demo.bootstrap import create_application
from pricing_demo.infrastructure.config.settings import Settings


def render_openapi() -> str:
    app = create_application(Settings(adapters="fake"))
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main(arguments: list[str]) -> int:
    if len(arguments) != 1:
        print("usage: python -m pricing_demo.export_openapi <path>", file=sys.stderr)
        return 2
    Path(arguments[0]).write_text(render_openapi(), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
