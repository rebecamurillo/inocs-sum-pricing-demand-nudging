"""Writes to one step of a run through the run queue's locked read-modify-write, for the
executors that report a step's key, its reason or its counts before the step ends."""

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.domain.runs import Run, RunStep


def write_step(queue: RunQueue, run_id: str, step: RunStep, **fields: Any) -> None:
    def change(run: Run) -> Run:
        steps = tuple(
            replace(item, **fields) if item.position == step.position else item
            for item in run.steps
        )
        return replace(run, steps=steps)

    queue.update(run_id, change)


def write_key(queue: RunQueue, run_id: str, step: RunStep, key: str) -> None:
    """Write the step's input key when it is not the one queued."""
    if key != step.input_key:
        write_step(queue, run_id, step, input_key=key)


def write_kept(
    queue: RunQueue, run_id: str, step: RunStep, reason: str, counts: Mapping[str, Any]
) -> None:
    """What a step that is kept shows: why, and what its stored result counted."""
    write_step(queue, run_id, step, reason=reason, counts=dict(counts))
