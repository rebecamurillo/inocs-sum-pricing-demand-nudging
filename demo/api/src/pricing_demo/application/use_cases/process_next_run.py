import logging
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import partial

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.application.ports.worker_registry import WorkerIdentity, WorkerRegistry
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.domain.run_recovery import STAGE_ERROR
from pricing_demo.domain.runs import (
    Run,
    RunFailure,
    RunState,
    RunStep,
    StepState,
    all_steps_complete,
    cancel_running,
    fail,
    succeed,
    transition_step,
)

logger = logging.getLogger(__name__)

# Seconds between two looks at the clock while a step runs; the worker also polls this often.
TICK_SECONDS = 1.0
HEARTBEAT_EVERY = timedelta(seconds=5)
CANCELLATION_CHECK_EVERY = timedelta(seconds=2)


@dataclass
class _Pulse:
    """When the running run was last heartbeated and last checked for a cancellation."""

    heartbeat: datetime
    cancellation_check: datetime


class ProcessNextRun:
    """Claim the oldest queued run and execute it, step by step, to its end.

    One run at a time: the call returns when the run has ended (or the worker was told to
    stop). Every write goes through `RunQueue.update`, a locked read-modify-write, so a
    cancellation request that lands meanwhile is never overwritten.
    """

    def __init__(
        self,
        queue: RunQueue,
        registry: StepRegistry,
        workers: WorkerRegistry,
        identity: WorkerIdentity,
        clock: Clock,
        waiter: Waiter,
    ) -> None:
        self._queue = queue
        self._registry = registry
        self._workers = workers
        self._identity = identity
        self._clock = clock
        self._waiter = waiter

    def execute(self, shutdown: threading.Event | None = None) -> bool:
        """False when no run was queued. `shutdown` set: stop the step, leave the run as it is."""
        claimed = self._queue.claim_next(self._identity.id, self._clock.now())
        if claimed is None:
            return False
        logger.info("Run %s claimed by %s", claimed.id, self._identity.id)
        now = self._clock.now()
        pulse = _Pulse(heartbeat=now, cancellation_check=now)
        self._process(claimed, pulse, shutdown or threading.Event())
        return True

    def _process(self, claimed: Run, pulse: _Pulse, shutdown: threading.Event) -> None:
        position_order = sorted(claimed.steps, key=lambda item: item.position)
        for planned in position_order:
            if planned.state in (StepState.DONE, StepState.KEPT):
                continue
            if shutdown.is_set():
                return
            run = self._queue.update(claimed.id, partial(self._begin, position=planned.position))
            if run.state is not RunState.RUNNING:
                return
            current = next(item for item in run.steps if item.position == planned.position)
            outcome = self._run_step(run, current, pulse, shutdown)
            if shutdown.is_set() and outcome.stopped:
                # Stopped by the worker's own stop: the run stays running for the next start.
                return
            run = self._queue.update(
                claimed.id, partial(self._end, position=planned.position, outcome=outcome)
            )
            if run.state is not RunState.RUNNING:
                return
        self._queue.update(claimed.id, self._finish)

    def _begin(self, run: Run, position: int) -> Run:
        now = self._clock.now()
        if run.cancel_requested_at is not None:
            return cancel_running(run, now)
        return _replace_step(
            run, position, lambda item: transition_step(item, StepState.RUNNING, now)
        )

    def _end(self, run: Run, position: int, outcome: StepOutcome) -> Run:
        now = self._clock.now()
        if outcome.stopped:
            return cancel_running(run, now)
        if outcome.failure_code is not None:
            code, reason = outcome.failure_code, outcome.failure_reason or ""
            failed_step = next(item for item in run.steps if item.position == position)
            marked = _replace_step(
                run,
                position,
                lambda item: replace(transition_step(item, StepState.FAILED, now), reason=reason),
            )
            return fail(marked, now, RunFailure(failed_step.step.value, code, reason))
        return _replace_step(
            run,
            position,
            lambda item: replace(
                transition_step(item, StepState.DONE, now), counts=dict(outcome.counts)
            ),
        )

    def _finish(self, run: Run) -> Run:
        if run.state is RunState.RUNNING and all_steps_complete(run):
            return succeed(run, self._clock.now())
        return run

    def _run_step(
        self, run: Run, step: RunStep, pulse: _Pulse, shutdown: threading.Event
    ) -> StepOutcome:
        executor = self._registry.executor_for(step.step)
        if executor is None:
            return StepOutcome.failed(
                STAGE_ERROR, f"no step executor is registered for {step.step.value}"
            )
        stop = threading.Event()
        finished = threading.Event()
        results: list[StepOutcome] = []

        def target() -> None:
            try:
                results.append(executor.execute(run, step, stop))
            except Exception as error:
                logger.exception("Step %s of run %s raised", step.step.value, run.id)
                results.append(StepOutcome.failed(STAGE_ERROR, f"{type(error).__name__}: {error}"))
            finally:
                finished.set()

        thread = threading.Thread(target=target, name=f"step-{run.id}-{step.step.value}")
        thread.start()
        try:
            while not self._waiter.wait(TICK_SECONDS, finished):
                if shutdown.is_set():
                    stop.set()
                try:
                    self._tick(run.id, pulse, stop)
                except Exception:
                    # A failed heartbeat or check must not abandon a step that is still
                    # running: its thread would outlive the run and overlap the next one.
                    logger.exception("The heartbeat of run %s failed; the step goes on", run.id)
        finally:
            if thread.is_alive():
                stop.set()
            thread.join()
        return results[0]

    def _tick(self, run_id: str, pulse: _Pulse, stop: threading.Event) -> None:
        now = self._clock.now()
        if now - pulse.heartbeat >= HEARTBEAT_EVERY:
            self._queue.heartbeat_run(run_id, now)
            self._workers.heartbeat(
                self._identity.id,
                self._identity.host,
                self._identity.pid,
                self._identity.started_at,
                now,
            )
            pulse.heartbeat = now
        if now - pulse.cancellation_check >= CANCELLATION_CHECK_EVERY:
            pulse.cancellation_check = now
            current = self._queue.get(run_id)
            if current is not None and current.cancel_requested_at is not None:
                stop.set()


def _replace_step(run: Run, position: int, change) -> Run:  # type: ignore[no-untyped-def]
    steps = tuple(change(item) if item.position == position else item for item in run.steps)
    return replace(run, steps=steps)
