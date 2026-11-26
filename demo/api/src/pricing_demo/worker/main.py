"""The worker's composition root and entry point (`pricing-demo-worker`).

Like `bootstrap` and `asgi` for the API, this is the one place that builds the worker's
adapters and injects them. The API and the worker share only PostgreSQL.
"""

import logging
import os
import signal
import socket
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from types import FrameType

from sqlalchemy import Engine

from pricing_demo.application.ports.component_probe import ComponentProbe
from pricing_demo.application.ports.worker_registry import WorkerIdentity
from pricing_demo.application.step_registry import StepRegistry
from pricing_demo.application.use_cases.process_next_run import ProcessNextRun
from pricing_demo.application.use_cases.recover_interrupted_runs import RecoverInterruptedRuns
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.application.use_cases.run_worker import RunWorker
from pricing_demo.domain.system_status import PROBED_COMPONENTS
from pricing_demo.infrastructure.clock import SystemClock
from pricing_demo.infrastructure.config.settings import Settings
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe
from pricing_demo.infrastructure.persistence.component_reports import PostgresComponentReports
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.persistence.run_repository import PostgresRunRepository
from pricing_demo.infrastructure.persistence.worker_registry import PostgresWorkerRegistry
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe
from pricing_demo.infrastructure.waiter import SystemWaiter

logger = logging.getLogger("pricing_demo.worker")


@dataclass(frozen=True)
class BuiltWorker:
    worker: RunWorker
    identity: WorkerIdentity
    engine: Engine


def worker_id_for(settings: Settings, host: str, pid: int) -> str:
    """`PRICING_DEMO_WORKER_ID` when set, otherwise `{host}-{pid}`."""
    return settings.worker_id or f"{host}-{pid}"


def build_probes(settings: Settings, engine: Engine) -> Sequence[ComponentProbe]:
    """The probes of the solver, the package and the trip planner, by adapter set. Only the
    worker builds them: the API process never loads the package."""
    if settings.adapters == "fake":
        fake_settings = PostgresFakeSettings(engine)
        return [FakeProbe(name, fake_settings) for name in PROBED_COMPONENTS]
    return [SolverProbe(), PackageProbe(), OtpProbe(settings.otp_url)]


def build_worker(settings: Settings) -> BuiltWorker:
    """Choose the adapters and wire them. Nothing here connects to the database."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_db_engine(settings.database_url)
    repository = PostgresRunRepository(engine)
    workers = PostgresWorkerRegistry(engine)
    clock = SystemClock()
    waiter = SystemWaiter()
    host, pid = socket.gethostname(), os.getpid()
    identity = WorkerIdentity(worker_id_for(settings, host, pid), host, pid, clock.now())
    # No step executor exists yet: story 2-5 registers the first. The `fake` and the `real`
    # adapter set therefore build the same registry for now.
    registry = StepRegistry()
    logger.info("Adapter set: %s; data directory: %s", settings.adapters, settings.data_dir)
    worker = RunWorker(
        identity,
        workers,
        RecoverInterruptedRuns(repository, clock),
        ProcessNextRun(repository, registry, workers, identity, clock, waiter),
        ReportComponents(
            build_probes(settings, engine), PostgresComponentReports(engine), identity.id, clock
        ),
        timedelta(seconds=settings.component_report_interval_s),
        clock,
        waiter,
    )
    return BuiltWorker(worker, identity, engine)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    built = build_worker(Settings())
    stop = threading.Event()

    def request_stop(signum: int, _: FrameType | None) -> None:
        logger.info("Signal %s: stopping", signum)
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logger.info("Worker %s starting (pid %s)", built.identity.id, built.identity.pid)
    try:
        built.worker.start()
        built.worker.run(stop)
    finally:
        built.engine.dispose()
        logger.info("Worker %s stopped", built.identity.id)


if __name__ == "__main__":
    main()
