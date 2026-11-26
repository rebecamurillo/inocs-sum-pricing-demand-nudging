"""The tables of the application, on the shared metadata. Migrations create the same shapes."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pricing_demo.infrastructure.persistence.metadata import metadata

RUN_KINDS = ("build", "pricing", "simulation")
RUN_STATES = ("queued", "running", "succeeded", "failed", "cancelled")
STEP_NAMES = (
    "area",
    "hubs",
    "routes",
    "travellers_and_bikes",
    "pricing_model",
    "traveller_simulation",
)
STEP_STATES = ("pending", "running", "done", "kept", "failed", "cancelled")

KIND_SUBJECT_CHECK = (
    "(kind = 'build' AND instance_version_id IS NOT NULL AND pricing_version_id IS NULL)"
    " OR (kind IN ('pricing', 'simulation') AND pricing_version_id IS NOT NULL"
    " AND instance_version_id IS NULL)"
)
ACTIVE_RUN_PREDICATE = "state IN ('queued', 'running')"


def one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


workers = Table(
    "workers",
    metadata,
    Column("id", Text, primary_key=True),
    Column("host", Text, nullable=False),
    Column("pid", Integer, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
)

runs = Table(
    "runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("instance_version_id", Text),
    Column("pricing_version_id", Text),
    Column("state", Text, nullable=False),
    Column("attempt", Integer, nullable=False, server_default=text("1")),
    Column("queued_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("heartbeat_at", DateTime(timezone=True)),
    Column("worker_id", Text, ForeignKey("workers.id")),
    Column("child_pid", Integer),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("failed_step", Text),
    Column("failure_code", Text),
    Column("failure_reason", Text),
    Column("failure_pct", Double),
    CheckConstraint(one_of("kind", RUN_KINDS), name="kind"),
    CheckConstraint(one_of("state", RUN_STATES), name="state"),
    CheckConstraint(KIND_SUBJECT_CHECK, name="kind_subject"),
    Index(
        "uq_runs_active_subject",
        text("coalesce(instance_version_id, pricing_version_id)"),
        unique=True,
        postgresql_where=text(ACTIVE_RUN_PREDICATE),
    ),
)

run_steps = Table(
    "run_steps",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("run_id", Text, ForeignKey("runs.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("step", Text, nullable=False),
    Column("period_id", Text),
    Column("state", Text, nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("counts", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("progress_done", Integer),
    Column("progress_total", Integer),
    Column("reason", Text),
    Column("input_key", Text),
    Column("peak_rss_bytes", BigInteger),
    Column("log_excerpt", Text),
    UniqueConstraint("run_id", "position", name="uq_run_steps_run_id_position"),
    CheckConstraint(one_of("step", STEP_NAMES), name="step"),
    CheckConstraint(one_of("state", STEP_STATES), name="state"),
)

COMPONENT_STATES = ("available", "limited", "unavailable")

# `worker_id` has no foreign key: the e2e reset truncates `workers` and the worker must still
# be able to write its reports. A report is fresh when the `workers` row it names beats.
component_reports = Table(
    "component_reports",
    metadata,
    Column("component", Text, primary_key=True),
    Column("state", Text, nullable=False),
    Column("reason", Text),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("reported_at", DateTime(timezone=True), nullable=False),
    Column("worker_id", Text, nullable=False),
    CheckConstraint(one_of("state", COMPONENT_STATES), name="state"),
)

# One row, written by the test-control routes; always empty with real adapters.
fake_settings = Table(
    "fake_settings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("settings", JSONB, nullable=False),
    CheckConstraint("id = 1", name="single_row"),
)
