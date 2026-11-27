import logging
import threading
from datetime import datetime, timedelta

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.application.ports.worker_registry import WorkerIdentity, WorkerRegistry
from pricing_demo.application.use_cases.collect_unreferenced import CollectUnreferenced
from pricing_demo.application.use_cases.process_next_run import (
    HEARTBEAT_EVERY,
    TICK_SECONDS,
    ProcessNextRun,
)
from pricing_demo.application.use_cases.record_package_fingerprint import (
    RecordPackageFingerprint,
)
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.report_components import ReportComponents

logger = logging.getLogger(__name__)

# How often the worker looks for interrupted runs, besides at its start, on the injected clock.
# A worker restarted within 60 s of its predecessor's last heartbeat, or a run abandoned after
# a failed write, is recovered by a later pass.
RECOVERY_EVERY = timedelta(seconds=10)

# How often the worker removes what no instance version references any more.
COLLECT_EVERY = timedelta(minutes=10)


class RunWorker:
    """The worker's loop: register, recover interrupted runs, report the components, then poll
    for queued runs.

    The recovery runs at the start and again every `RECOVERY_EVERY`, idle or while a run
    executes; it never recovers the run this worker has in hand. The components are reported
    at the start and again every `report_every`, in the same way; a failed report is logged
    and tried again at the next tick.
    """

    def __init__(
        self,
        identity: WorkerIdentity,
        workers: WorkerRegistry,
        recover: RecoverInterruptedRuns,
        process: ProcessNextRun,
        report: ReportComponents,
        report_every: timedelta,
        clock: Clock,
        waiter: Waiter,
        fingerprint: RecordPackageFingerprint,
        *,
        collect: CollectUnreferenced | None = None,
    ) -> None:
        self._identity = identity
        self._workers = workers
        self._recover = recover
        self._process = process
        self._report = report
        self._report_every = report_every
        self._clock = clock
        self._waiter = waiter
        self._fingerprint = fingerprint
        self._last_recovery: datetime | None = None
        self._last_report: datetime | None = None
        self._collect = collect
        self._last_collection: datetime | None = None

    def start(self) -> None:
        identity = self._identity
        self._workers.register(
            identity.id,
            identity.host,
            identity.pid,
            self._clock.now(),
            self._fingerprint.execute(),
        )
        self._report_if_due()
        self._recover_now(None)
        self._collect_if_due()

    def _report_if_due(self) -> None:
        last = self._last_report
        if last is not None and self._clock.now() - last < self._report_every:
            return
        started = self._clock.now()
        try:
            self._report.execute()
        except Exception:
            logger.exception("The report of the components failed; trying again")
            return
        self._last_report = started

    def _collect_if_due(self) -> None:
        if self._collect is None:
            return
        last = self._last_collection
        if last is not None and self._clock.now() - last < COLLECT_EVERY:
            return
        started = self._clock.now()
        try:
            self._collect.execute()
        except Exception:
            logger.exception("The collection of unreferenced artefacts failed; trying again")
            return
        self._last_collection = started

    def _recover_now(self, in_hand: str | None) -> None:
        self._last_recovery = self._clock.now()
        for run in self._recover.execute(in_hand):
            logger.warning("Run %s was interrupted: it is now %s", run.id, run.state.value)

    def _periodic(self, in_hand: str | None) -> None:
        self._report_if_due()
        self._collect_if_due()
        last = self._last_recovery
        if last is None or self._clock.now() - last >= RECOVERY_EVERY:
            self._recover_now(in_hand)

    def run(self, until: threading.Event) -> None:
        """Poll every second until `until` is set. A run in progress stays as it is on stop."""
        last_heartbeat: datetime | None = self._clock.now()
        while not until.is_set():
            idle = True
            try:
                self._periodic(None)
            except Exception:
                logger.exception("The recovery of interrupted runs failed; trying again")
            try:
                if last_heartbeat is None:
                    # After a failure, write the workers row before claiming: a claim names
                    # the worker (foreign key), and an e2e reset may have deleted the row.
                    last_heartbeat = self._clock.now()
                    self._heartbeat(last_heartbeat)
                idle = not self._process.execute(until, self._periodic)
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
        self._workers.heartbeat(
            identity.id,
            identity.host,
            identity.pid,
            identity.started_at,
            at,
            self._fingerprint.execute(),
        )
