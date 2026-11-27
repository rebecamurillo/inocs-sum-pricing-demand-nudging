"""The stage child: runs one step of the package in its own process.

Usage: `python -m pricing_demo.infrastructure.pricing_model.stage_runner {spec.json}`. The worker
(`stage_child.py`) starts it in its own session and process group, with the step's working
directory as current directory. It leaves `outcome.json` (`status` and `counts`, or the
exception's type, message and traceback), `progress.jsonl` (the package's log records) and, as
its output, `stdout.log` and `stderr.log`. The package is imported only here, inside `run`.
"""

import json
import logging
import os
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pricing_demo.infrastructure.pricing_model.stage_spec import (
    OUTCOME_FILE,
    PROGRESS_FILE,
    StageSpec,
)

PACKAGE_LOGGER = "sum_nsm_dynamic_pricing"
PARENT_GONE = 3
WATCH_EVERY_S = 2.0
# The name the store expects for the file the package names after its pair count.
INSTANCE_FILE = "Instance_1.json"
BIKE_LEGS_FILE = "option_bike_legs.json"


class ProgressHandler(logging.Handler):
    """Appends one JSON line per log record: its time, logger, level, template and arguments."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path
        # The file exists even when the step logs nothing.
        path.touch()

    def emit(self, record: logging.LogRecord) -> None:
        args = record.args if isinstance(record.args, tuple) else (record.args,)
        line = {
            "created": record.created,
            "logger": record.name,
            "level": record.levelname,
            "template": str(record.msg),
            "args": [_plain(item) for item in args],
        }
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(line) + "\n")


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def watch_parent(
    parent_pid: int,
    getppid: Callable[[], int],
    exit_now: Callable[[], None],
    wait: Callable[[float], None],
    every: float = WATCH_EVERY_S,
) -> None:
    """Ends the child once its parent is gone (it is then adopted: `getppid` changes). Loops
    until `exit_now` returns, so a real `os._exit` never comes back."""
    while True:
        wait(every)
        if getppid() != parent_pid:
            exit_now()
            return


def write_outcome(path: Path, outcome: dict[str, Any]) -> None:
    """Writes under a temporary name, then renames: the worker never reads half a file."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(outcome), encoding="utf-8")
    os.replace(temporary, path)


def failure_outcome(error: BaseException) -> dict[str, Any]:
    return {
        "status": "error",
        "exception_type": type(error).__name__,
        "message": str(error),
        "traceback": "".join(traceback.format_exception(error)),
    }


def keep_object_strings() -> None:
    """Workaround for model-notes entry 24: with pandas 3 the package's `hub_builder.py:33`
    meets a string array that is not a numpy array. Strings stay `object`, as the package was
    written for; the package is not edited."""
    import warnings

    import pandas as pd

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pd.set_option("future.infer_string", False)


def run(spec: StageSpec) -> dict[str, Any]:
    """Runs the step with the package and returns what `outcome.json` holds."""
    from sum_nsm_dynamic_pricing.config import InstanceParams, PipelineConfig
    from sum_nsm_dynamic_pricing.optimizer.parser import parse_json_instance
    from sum_nsm_dynamic_pricing.pipeline import InstancePipeline

    keep_object_strings()
    folder = Path(spec.working_dir)
    os.chdir(folder)
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.setLevel(logging.INFO)
    logger.addHandler(ProgressHandler(folder / PROGRESS_FILE))
    fields = dict(spec.pipeline)
    for name in ("gtfs_path", "gbfs_path"):
        if fields.get(name) is not None:
            fields[name] = Path(fields[name])
    pipeline = InstancePipeline(PipelineConfig(output_dir=folder, **fields))
    if spec.step == "area":
        pipeline.prepare_stations()
    elif spec.step == "hubs":
        pipeline.build_hubs()
    else:
        written = pipeline.generate_instance(InstanceParams(**spec.instance))
        target = folder / INSTANCE_FILE
        if written != target:
            os.replace(written, target)
        parsed = parse_json_instance(target)
        bike_legs = {str(arc_id): legs for (_, _, arc_id), legs in parsed["k_bike_legs"].items()}
        (folder / BIKE_LEGS_FILE).write_text(json.dumps(bike_legs, sort_keys=True), "utf-8")
    return {"status": "done", "counts": {}}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: stage_runner <spec.json>", file=sys.stderr)
        return 2
    spec = StageSpec.from_json(Path(argv[0]).read_text(encoding="utf-8"))
    threading.Thread(
        target=watch_parent,
        args=(spec.parent_pid, os.getppid, lambda: os._exit(PARENT_GONE), time.sleep),
        daemon=True,
    ).start()
    try:
        outcome = run(spec)
        code = 0
    except Exception as error:
        traceback.print_exc()
        outcome, code = failure_outcome(error), 1
    write_outcome(Path(spec.working_dir) / OUTCOME_FILE, outcome)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
