import json
import logging
from pathlib import Path

from pricing_demo.infrastructure.pricing_model.stage_runner import (
    ProgressHandler,
    failure_outcome,
    watch_parent,
    write_outcome,
)
from pricing_demo.infrastructure.pricing_model.stage_spec import StageSpec


def test_the_handler_writes_one_json_line_per_record_with_its_template_and_arguments(
    tmp_path: Path,
) -> None:
    path = tmp_path / "progress.jsonl"
    logger = logging.getLogger("test_stage_runner.handler")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = ProgressHandler(path)
    logger.addHandler(handler)
    try:
        logger.info("Routed %s of %d (%s)", "pair", 3, Path("x"))
        logger.warning("no args")
    finally:
        logger.removeHandler(handler)

    first, second = [json.loads(line) for line in path.read_text().splitlines()]
    assert first["template"] == "Routed %s of %d (%s)"
    assert first["args"] == ["pair", 3, "x"]
    assert (first["logger"], first["level"]) == ("test_stage_runner.handler", "INFO")
    assert isinstance(first["created"], float)
    assert second["args"] == []


def test_the_watch_exits_once_the_parent_pid_changes_and_not_before() -> None:
    pids = iter([10, 10, 10, 1])
    waits: list[float] = []
    exits: list[bool] = []

    watch_parent(10, lambda: next(pids), lambda: exits.append(True), waits.append)

    assert waits == [2.0] * 4
    assert exits == [True]


def test_an_outcome_is_written_whole_or_not_at_all(tmp_path: Path) -> None:
    path = tmp_path / "outcome.json"

    write_outcome(path, {"status": "done", "counts": {}})

    assert json.loads(path.read_text()) == {"status": "done", "counts": {}}
    assert [item.name for item in tmp_path.iterdir()] == ["outcome.json"]


def test_a_failure_outcome_holds_the_type_message_and_traceback() -> None:
    try:
        raise ValueError("bad")
    except ValueError as error:
        outcome = failure_outcome(error)

    assert outcome["status"] == "error"
    assert (outcome["exception_type"], outcome["message"]) == ("ValueError", "bad")
    assert "Traceback" in outcome["traceback"]


def test_a_spec_round_trips_through_json() -> None:
    spec = StageSpec("hubs", "/w", 7, {"radius_m": 500, "gtfs_path": "/g.zip"}, {"min_demand": 1})

    assert StageSpec.from_json(spec.to_json()) == spec
