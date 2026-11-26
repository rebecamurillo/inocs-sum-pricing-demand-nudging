"""What becomes of a running run whose worker stopped: queued again once, then failed."""

from dataclasses import replace
from datetime import datetime, timedelta

from pricing_demo.domain.runs import (
    Run,
    RunFailure,
    RunState,
    StepState,
    fail,
    requeue_after_interruption,
    transition_step,
)

STALE_AFTER = timedelta(seconds=60)
MAX_ATTEMPTS = 2
INTERRUPTED_CODE = "interrupted"
INTERRUPTED_REASON = "The run was interrupted twice by a stop of the runner"
STAGE_ERROR = "stage_error"


def is_stale(run: Run, now: datetime) -> bool:
    """A running run whose last heartbeat is more than 60 s old, or that never had one."""
    if run.state is not RunState.RUNNING:
        return False
    if run.heartbeat_at is None:
        return True
    return now - run.heartbeat_at > STALE_AFTER


def recover_interrupted(run: Run, now: datetime) -> Run:
    """Queue a stale run again for its second attempt; fail it when it is already on its second."""
    if run.attempt < MAX_ATTEMPTS:
        return requeue_after_interruption(run)
    failed_step: str | None = None
    steps = []
    for item in run.steps:
        if item.state is StepState.RUNNING and failed_step is None:
            failed_step = item.step.value
            item = replace(transition_step(item, StepState.FAILED, now), reason=INTERRUPTED_REASON)
        steps.append(item)
    failure = RunFailure(step=failed_step, code=INTERRUPTED_CODE, reason=INTERRUPTED_REASON)
    return replace(fail(run, now, failure), steps=tuple(steps))
