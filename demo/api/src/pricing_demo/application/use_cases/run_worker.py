import logging
import threading
from datetime import datetime, timedelta

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.application.ports.worker_registry import WorkerIdentity, WorkerRegistry
from pricing_demo.application.use_cases.process_next_run import (
    HEARTBEAT_EVERY,
    TICK_SECONDS,
    ProcessNextRun,
)
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns

logger = logging.getLogger(__name__)

# How often the worker looks for interrupted runs, besides at its start, on the injected clock.
# A worker restarted within 60 s of its predecessor's last heartbeat, or a run abandoned after
# a failed write, is recovered by a later pass.
RECOVERY_EVERY = timedelta(seconds=10)


class RunWorker:
    """The worker's loop: register, recover interrupted runs, then poll for queued runs.

    The recovery runs at the start and again every `RECOVERY_EVERY`, idle or while a run
    executes; it never recovers the run this worker has in hand.
    """

    def __init__(
        self,
        identity: WorkerIdentity,
        workers: WorkerRegistry,
        recover: RecoverInterruptedRuns,
        process: ProcessNextRun,
        clock: Clock,
        waiter: Waiter,
    ) -> None:
        self._identity = identity
        self._workers = workers
        self._recover = recover
        self._process = process
        self._clock = clock
        self._waiter = waiter
        self._last_recovery: datetime | None = None

    def start(self) -> None:
        identity = self._identity
        self._workers.register(identity.id, identity.host, identity.pid, self._clock.now())
        self._recover_now(None)

    def _recover_now(self, in_hand: str | None) -> None:
        self._last_recovery = self._clock.now()
        for run in self._recover.execute(in_hand):
            logger.warning("Run %s was interrupted: it is now %s", run.id, run.state.value)

    def _recover_if_due(self, in_hand: str | None) -> None:
        last = self._last_recovery
        if last is None or self._clock.now() - last >= RECOVERY_EVERY:
            self._recover_now(in_hand)

    def run(self, until: threading.Event) -> None:
        """Poll every second until `until` is set. A run in progress stays as it is on stop."""
        last_heartbeat: datetime | None = self._clock.now()
        while not until.is_set():
            idle = True
            try:
                self._recover_if_due(None)
            except Exception:
                logger.exception("The recovery of interrupted runs failed; trying again")
            try:
                if last_heartbeat is None:
                    # After a failure, write the workers row before claiming: a claim names
                    # the worker (foreign key), and an e2e reset may have deleted the row.
                    last_heartbeat = self._clock.now()
                    self._heartbeat(last_heartbeat)
                idle = not self._process.execute(until, self._recover_if_due)
                now = self._clock.now()
                if last_heartbeat is None or now - last_heartbeat >= HEARTBEAT_EVERY:
                    self._heartbeat(now)
                    last_heartbeat = now
            except Exception:
                # A database that restarts must not end the worker; the heartbeat that follows
                # also re-creates a workers row the e2e reset deleted.
                logger.exception("The worker's loop failed; trying again")
                last_heartbeat = None
            if idle:
                self._waiter.wait(TICK_SECONDS, until)

    def _heartbeat(self, at: datetime) -> None:
        identity = self._identity
        self._workers.heartbeat(identity.id, identity.host, identity.pid, identity.started_at, at)
