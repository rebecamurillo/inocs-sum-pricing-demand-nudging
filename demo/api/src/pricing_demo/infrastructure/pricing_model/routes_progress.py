"""What the worker reads from the routes child's `progress.jsonl`: the package's log records
of step 3, as the total, the queries done and the failed queries (AC2 of story 2-8).

Pure: the package is not imported. The templates are the exact `record.msg` texts of the
package (`route_builder.py`, `quality.py`); `make test-model` pins them.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pricing_demo.domain.read_model import RouteFailure

# `route_builder.py:277-278`: two literals concatenated.
ROUTE_TOTAL = (
    "Route building: %d total OD pairs | %d already cached | %d to query (workers=%d, delay=%.2fs)"
)
PT_FAILED = "OTP PT query failed for pair %s: %s"
PT_NONE = "No PT patterns returned for pair %s"
PT_UNCLASSIFIED = "All %d pattern(s) for pair %s were unclassified (no PT/bike modes)"
CAR_DONE = "OTP CAR [%s]: car=%d"
CAR_FAILED = "OTP CAR query failed for pair %s: %s"
CLEANUP_REMOVED = "OD cleanup removed %d/%d OD pairs (%.2f%% invalid) from %s"


class RoutesProgress:
    """Folds the records into the counts; `feed` returns the failures a record carries."""

    def __init__(self, retries: int) -> None:
        self._attempts = 1 + retries
        self.done = 0
        self.total = 0
        self.removed = 0

    def feed(self, record: Mapping[str, Any]) -> list[RouteFailure]:
        template = record.get("template")
        args = list(record.get("args") or [])
        try:
            return self._feed(template, args)
        except (IndexError, TypeError, ValueError):
            return []

    def _feed(self, template: object, args: list[Any]) -> list[RouteFailure]:
        if template == ROUTE_TOTAL:
            self.total = int(args[0])
            return []
        if template == CLEANUP_REMOVED:
            self.removed = int(args[0])
            return []
        if template == PT_FAILED:
            return self._failure(template, args, args[0], "pt_bike", "technical")
        if template == PT_NONE:
            return self._failure(template, args, args[0], "pt_bike", "no_route")
        if template == PT_UNCLASSIFIED:
            return self._failure(template, args, args[1], "pt_bike", "no_route")
        if template == CAR_FAILED:
            return self._failure(template, args, args[0], "car", "technical")
        if template == CAR_DONE:
            if int(args[1]) == 0:
                return self._failure(template, args, args[0], "car", "no_route")
            self.done += 1
        return []

    def _failure(
        self, template: str, args: list[Any], pair: object, query: Any, kind: Any
    ) -> list[RouteFailure]:
        origin, _, destination = str(pair).partition("|")
        self.done += 1
        attempts = self._attempts if kind == "technical" else 1
        return [RouteFailure(origin, destination, query, kind, template % tuple(args), attempts)]


class ProgressFile:
    """Reads the complete lines of `progress.jsonl` that were not read yet."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._offset = 0

    def read_new(self) -> list[dict[str, Any]]:
        try:
            with self._path.open("rb") as file:
                file.seek(self._offset)
                data = file.read()
        except OSError:
            return []
        end = data.rfind(b"\n") + 1
        self._offset += end
        records = []
        for line in data[:end].splitlines():
            try:
                found = json.loads(line)
            except ValueError:
                continue
            if isinstance(found, dict):
                records.append(found)
        return records
