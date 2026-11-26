from collections.abc import Callable, Collection
from datetime import datetime
from typing import Any

from sqlalchemy import Connection, Engine, func, insert, select, update

from pricing_demo.domain.runs import (
    Run,
    RunFailure,
    RunKind,
    RunNotFound,
    RunState,
    RunStep,
    StepName,
    StepState,
    Subject,
    SubjectType,
    start,
)
from pricing_demo.infrastructure.persistence.tables import run_steps, runs, workers


class PostgresRunRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, run: Run) -> None:
        with self._engine.begin() as connection:
            connection.execute(insert(runs).values(_run_values(run)))
            if run.steps:
                connection.execute(
                    insert(run_steps), [_step_values(run.id, item) for item in run.steps]
                )

    def get(self, run_id: str) -> Run | None:
        with self._engine.connect() as connection:
            row = connection.execute(select(runs).where(runs.c.id == run_id)).mappings().first()
            if row is None:
                return None
            steps = _steps_of(connection.execute(_steps_query([run_id])).mappings())
            return _run_of(row, steps.get(run_id, ()))

    def list_by_states(self, states: Collection[RunState]) -> list[Run]:
        if not states:
            return []
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    select(runs)
                    .where(runs.c.state.in_([state.value for state in states]))
                    .order_by(runs.c.queued_at, runs.c.id)
                )
                .mappings()
                .all()
            )
            steps = _steps_of(
                connection.execute(_steps_query([row["id"] for row in rows])).mappings()
            )
        return [_run_of(row, steps.get(row["id"], ())) for row in rows]

    def latest_worker_heartbeat(self) -> datetime | None:
        with self._engine.connect() as connection:
            latest: datetime | None = connection.execute(
                select(func.max(workers.c.heartbeat_at))
            ).scalar_one()
            return latest

    def save(self, run: Run) -> None:
        """Overwrite the stored run. Not safe against a concurrent writer: use `update`."""
        with self._engine.begin() as connection:
            _write_run(connection, run)

    def update(self, run_id: str, change: Callable[[Run], Run]) -> Run:
        with self._engine.begin() as connection:
            row = (
                connection.execute(select(runs).where(runs.c.id == run_id).with_for_update())
                .mappings()
                .first()
            )
            if row is None:
                raise RunNotFound(f"No run has the id {run_id}.")
            steps = _steps_of(connection.execute(_steps_query([run_id])).mappings())
            changed = change(_run_of(row, steps.get(run_id, ())))
            _write_run(connection, changed)
            return changed

    def claim_next(self, worker_id: str, at: datetime) -> Run | None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    select(runs)
                    .where(runs.c.state == RunState.QUEUED.value)
                    .order_by(runs.c.queued_at, runs.c.id)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            steps = _steps_of(connection.execute(_steps_query([row["id"]])).mappings())
            claimed = start(_run_of(row, steps.get(row["id"], ())), at, worker_id)
            _write_run(connection, claimed)
            return claimed

    def heartbeat_run(self, run_id: str, at: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                update(runs)
                .where(runs.c.id == run_id, runs.c.state == RunState.RUNNING.value)
                .values(heartbeat_at=at)
            )

    def running_runs(self) -> list[Run]:
        return self.list_by_states([RunState.RUNNING])


def _write_run(connection: Connection, run: Run) -> None:
    values = _run_values(run)
    del values["id"]
    result = connection.execute(update(runs).where(runs.c.id == run.id).values(values))
    if result.rowcount == 0:
        raise KeyError(run.id)
    for item in run.steps:
        connection.execute(
            update(run_steps)
            .where(run_steps.c.run_id == run.id, run_steps.c.position == item.position)
            .values(_step_values(run.id, item))
        )


def _steps_query(run_ids: list[str]) -> Any:
    return (
        select(run_steps)
        .where(run_steps.c.run_id.in_(run_ids))
        .order_by(run_steps.c.run_id, run_steps.c.position)
    )


def _subject_columns(run: Run) -> dict[str, str | None]:
    is_instance = run.subject.type is SubjectType.INSTANCE_VERSION
    return {
        "instance_version_id": run.subject.id if is_instance else None,
        "pricing_version_id": None if is_instance else run.subject.id,
    }


def _run_values(run: Run) -> dict[str, Any]:
    failure = run.failure
    return {
        "id": run.id,
        "kind": run.kind.value,
        **_subject_columns(run),
        "state": run.state.value,
        "attempt": run.attempt,
        "queued_at": run.queued_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "heartbeat_at": run.heartbeat_at,
        "worker_id": run.worker_id,
        "child_pid": run.child_pid,
        "cancel_requested_at": run.cancel_requested_at,
        "failed_step": failure.step if failure else None,
        "failure_code": failure.code if failure else None,
        "failure_reason": failure.reason if failure else None,
        "failure_pct": run.failure_pct,
    }


def _step_values(run_id: str, step: RunStep) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "position": step.position,
        "step": step.step.value,
        "period_id": step.period,
        "state": step.state.value,
        "started_at": step.started_at,
        "finished_at": step.finished_at,
        "counts": dict(step.counts),
        "progress_done": step.progress_done,
        "progress_total": step.progress_total,
        "reason": step.reason,
        "input_key": step.input_key,
        "peak_rss_bytes": step.peak_rss_bytes,
        "log_excerpt": step.log_excerpt,
    }


def _steps_of(rows: Any) -> dict[str, tuple[RunStep, ...]]:
    grouped: dict[str, list[RunStep]] = {}
    for row in rows:
        grouped.setdefault(row["run_id"], []).append(_step_of(row))
    return {run_id: tuple(items) for run_id, items in grouped.items()}


def _step_of(row: Any) -> RunStep:
    return RunStep(
        position=row["position"],
        step=StepName(row["step"]),
        state=StepState(row["state"]),
        period=row["period_id"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        counts=row["counts"],
        progress_done=row["progress_done"],
        progress_total=row["progress_total"],
        reason=row["reason"],
        input_key=row["input_key"],
        peak_rss_bytes=row["peak_rss_bytes"],
        log_excerpt=row["log_excerpt"],
    )


def _run_of(row: Any, steps: tuple[RunStep, ...]) -> Run:
    if row["instance_version_id"] is not None:
        subject = Subject(SubjectType.INSTANCE_VERSION, row["instance_version_id"])
    else:
        subject = Subject(SubjectType.PRICING_VERSION, row["pricing_version_id"])
    failure = (
        RunFailure(row["failed_step"], row["failure_code"], row["failure_reason"])
        if row["failure_code"] is not None
        else None
    )
    return Run(
        id=row["id"],
        kind=RunKind(row["kind"]),
        subject=subject,
        state=RunState(row["state"]),
        queued_at=row["queued_at"],
        attempt=row["attempt"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        heartbeat_at=row["heartbeat_at"],
        worker_id=row["worker_id"],
        child_pid=row["child_pid"],
        cancel_requested_at=row["cancel_requested_at"],
        failure=failure,
        failure_pct=row["failure_pct"],
        steps=steps,
    )
