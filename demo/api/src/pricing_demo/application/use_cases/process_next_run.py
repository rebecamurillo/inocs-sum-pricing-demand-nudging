import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import partial
from typing import Any

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
    """When the running run was last heartbeated and last checked for a cancellation.

    `on_tick` is called with the run's id at every tick while a step runs: the worker's loop
    uses it to run its periodic recovery of the other runs.
    """

    heartbeat: datetime
    cancellation_check: datetime
    on_tick: Callable[[str], None] | None = None


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

    def execute(
        self,
        shutdown: threading.Event | None = None,
        on_tick: Callable[[str], None] | None = None,
    ) -> bool:
        """False when no run was queued. `shutdown` set: stop the step, leave the run as it is.

        `on_tick(run_id)` is called at every tick while a step of the claimed run runs.
        """
        claimed = self._queue.claim_next(self._identity.id, self._clock.now())
        if claimed is None:
            return False
        logger.info("Run %s claimed by %s", claimed.id, self._identity.id)
        now = self._clock.now()
        pulse = _Pulse(heartbeat=now, cancellation_check=now, on_tick=on_tick)
        self._process(claimed, pulse, shutdown or threading.Event())
        return True

    def _process(self, claimed: Run, pulse: _Pulse, shutdown: threading.Event) -> None:
        position_order = sorted(claimed.steps, key=lambda item: item.position)
        for planned in position_order:
            if planned.state in (StepState.DONE, StepState.KEPT):
                continue
            if shutdown.is_set():
                return
            if self._is_kept(claimed.id, planned):
                run = self._queue.update(claimed.id, partial(self._keep, position=planned.position))
                if run.state is not RunState.RUNNING:
                    return
                continue
            run = self._queue.update(claimed.id, partial(self._begin, position=planned.position))
            if run.state is not RunState.RUNNING:
                return
            current = next(item for item in run.steps if item.position == planned.position)
            outcome = self._run_step(run, current, pulse, shutdown)
            if shutdown.is_set() and outcome.stopped:
                # Stopped by the worker's own stop: the run stays running for the next start.
                return
            try:
                run = self._queue.update(
                    claimed.id, partial(self._end, position=planned.position, outcome=outcome)
                )
            except Exception as error:
                # The run is abandoned: its heartbeat stops here, and the periodic recovery
                # treats it as interrupted once the heartbeat is more than 60 s old.
                logger.exception(
                    "The end of step %s of run %s could not be written (%s: %s); "
                    "the run is abandoned to the recovery",
                    planned.step.value,
                    claimed.id,
                    type(error).__name__,
                    error,
                )
                return
            if run.state is not RunState.RUNNING:
                return
        self._queue.update(claimed.id, self._finish)

    def _is_kept(self, run_id: str, planned: RunStep) -> bool:
        """Ask the step's keeper, if it has one, whether the step needs no work. A keeper that
        raises is logged and the step runs: its executor then reports what is wrong."""
        keeper = self._registry.keeper_for(planned.step)
        if keeper is None:
            return False
        current = self._queue.get(run_id)
        if current is None or current.state is not RunState.RUNNING:
            return False
        step = next(item for item in current.steps if item.position == planned.position)
        try:
            return keeper.keep(current, step)
        except Exception:
            logger.exception("The keeper of step %s of run %s raised", planned.step.value, run_id)
            return False

    def _keep(self, run: Run, position: int) -> Run:
        now = self._clock.now()
        if run.cancel_requested_at is not None:
            return cancel_running(run, now)
        return _replace_step(run, position, lambda item: transition_step(item, StepState.KEPT, now))

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
                lambda item: replace(
                    transition_step(item, StepState.FAILED, now),
                    reason=reason,
                    **_child_output(outcome),
                ),
            )
            return fail(marked, now, RunFailure(failed_step.step.value, code, reason))
        return _replace_step(
            run,
            position,
            lambda item: replace(
                transition_step(item, StepState.DONE, now),
                counts=dict(outcome.counts),
                **_child_output(outcome),
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
                if pulse.on_tick is not None:
                    try:
                        pulse.on_tick(run.id)
                    except Exception:
                        logger.exception("The tick of run %s failed; the step goes on", run.id)
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


def _child_output(outcome: StepOutcome) -> dict[str, Any]:
    """The log excerpt and peak memory a child process left, only when it left them."""
    found: dict[str, Any] = {}
    if outcome.log_excerpt is not None:
        found["log_excerpt"] = outcome.log_excerpt
    if outcome.peak_rss_bytes is not None:
        found["peak_rss_bytes"] = outcome.peak_rss_bytes
    return found


def _replace_step(run: Run, position: int, change) -> Run:  # type: ignore[no-untyped-def]
    steps = tuple(change(item) if item.position == position else item for item in run.steps)
    return replace(run, steps=steps)
