"""Runs, their steps and the workers that take them.

Revision ID: 3b8e5d1f9a62
Revises: 7c1f3a9e2b40
Create Date: 2026-11-26 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3b8e5d1f9a62"
down_revision: str | None = "7c1f3a9e2b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The subject columns hold instance-version and pricing-version ids as text without foreign
# keys: those tables are created by later migrations.

# The values are written out here, not imported from tables.py: a merged migration must keep
# creating the same schema when the application's tables change later.
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


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("host", sa.Text, nullable=False),
        sa.Column("pid", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workers"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("instance_version_id", sa.Text),
        sa.Column("pricing_version_id", sa.Text),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("worker_id", sa.Text),
        sa.Column("child_pid", sa.Integer),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("failed_step", sa.Text),
        sa.Column("failure_code", sa.Text),
        sa.Column("failure_reason", sa.Text),
        sa.Column("failure_pct", sa.Double),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name="fk_runs_worker_id_workers"),
        sa.CheckConstraint(one_of("kind", RUN_KINDS), name=op.f("ck_runs_kind")),
        sa.CheckConstraint(one_of("state", RUN_STATES), name=op.f("ck_runs_state")),
        sa.CheckConstraint(KIND_SUBJECT_CHECK, name=op.f("ck_runs_kind_subject")),
    )
    op.create_index(
        "uq_runs_active_subject",
        "runs",
        [sa.text("coalesce(instance_version_id, pricing_version_id)")],
        unique=True,
        postgresql_where=sa.text(ACTIVE_RUN_PREDICATE),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", sa.BigInteger, sa.Identity(), nullable=False),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("step", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column(
            "counts",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("progress_done", sa.Integer),
        sa.Column("progress_total", sa.Integer),
        sa.Column("reason", sa.Text),
        sa.Column("input_key", sa.Text),
        sa.Column("peak_rss_bytes", sa.BigInteger),
        sa.Column("log_excerpt", sa.Text),
        sa.PrimaryKeyConstraint("id", name="pk_run_steps"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name="fk_run_steps_run_id_runs"),
        sa.UniqueConstraint("run_id", "position", name="uq_run_steps_run_id_position"),
        sa.CheckConstraint(one_of("step", STEP_NAMES), name=op.f("ck_run_steps_step")),
        sa.CheckConstraint(one_of("state", STEP_STATES), name=op.f("ck_run_steps_state")),
    )


def downgrade() -> None:
    op.drop_table("run_steps")
    op.drop_index("uq_runs_active_subject", table_name="runs")
    op.drop_table("runs")
    op.drop_table("workers")
