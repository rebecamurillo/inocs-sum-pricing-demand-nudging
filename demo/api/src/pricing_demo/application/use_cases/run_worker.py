import logging
import threading
from datetime import datetime

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


class RunWorker:
    """The worker's loop: register, recover interrupted runs, then poll for queued runs."""

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

    def start(self) -> None:
        identity = self._identity
        self._workers.register(identity.id, identity.host, identity.pid, self._clock.now())
        for run in self._recover.execute():
            logger.warning("Run %s was interrupted: it is now %s", run.id, run.state.value)

    def run(self, until: threading.Event) -> None:
        """Poll every second until `until` is set. A run in progress stays as it is on stop."""
        last_heartbeat: datetime | None = self._clock.now()
        while not until.is_set():
            idle = True
            try:
                if last_heartbeat is None:
                    # After a failure, write the workers row before claiming: a claim names
                    # the worker (foreign key), and an e2e reset may have deleted the row.
                    last_heartbeat = self._clock.now()
                    self._heartbeat(last_heartbeat)
                idle = not self._process.execute(until)
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
