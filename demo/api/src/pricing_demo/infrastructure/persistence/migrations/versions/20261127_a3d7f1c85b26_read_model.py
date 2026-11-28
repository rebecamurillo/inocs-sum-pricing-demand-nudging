"""The read model of a built instance, keyed by the artefact each row was ingested from, and the
failed trip-planner queries of a run.

Revision ID: a3d7f1c85b26
Revises: e9a2c6b4d1f7
Create Date: 2026-11-27 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3d7f1c85b26"
down_revision: str | None = "e9a2c6b4d1f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values are written out here, not imported from tables.py: a merged migration must keep
# creating the same schema when the application's tables change later.
READ_MODEL_TABLES = (
    "option_station_deltas",
    "station_bikes",
    "route_options",
    "hub_pairs",
    "station_hubs",
    "hubs",
    "stations",
)


def key_column(name: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.Text, nullable=False)


def key_constraint(table: str, column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column],
        ["artifacts.input_key"],
        name=f"fk_{table}_{column}_artifacts",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("run_id", sa.Text, nullable=True))
    op.create_foreign_key(
        "fk_artifacts_run_id_runs", "artifacts", "runs", ["run_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column(
        "artifacts",
        sa.Column(
            "reported_counts",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("artifacts", sa.Column("counts", postgresql.JSONB, nullable=True))
    op.add_column("artifacts", sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "stations",
        key_column("stations_key"),
        key_column("station_id"),
        key_column("kind"),
        key_column("name"),
        sa.Column("lat", sa.Double, nullable=False),
        sa.Column("lon", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint("stations_key", "station_id", name="pk_stations"),
        key_constraint("stations", "stations_key"),
        sa.CheckConstraint("kind IN ('pt', 'bs')", name=op.f("ck_stations_kind")),
    )
    op.create_table(
        "hubs",
        key_column("hubs_key"),
        key_column("hub_id"),
        key_column("label"),
        sa.Column("lat", sa.Double, nullable=False),
        sa.Column("lon", sa.Double, nullable=False),
        sa.Column("outline", postgresql.JSONB, nullable=True),
        sa.Column("pt_station_ids", postgresql.JSONB, nullable=False),
        sa.Column("bike_station_ids", postgresql.JSONB, nullable=False),
        sa.Column("lines", postgresql.JSONB, nullable=False),
        sa.PrimaryKeyConstraint("hubs_key", "hub_id", name="pk_hubs"),
        key_constraint("hubs", "hubs_key"),
    )
    op.create_table(
        "station_hubs",
        key_column("hubs_key"),
        key_column("station_id"),
        key_column("hub_id"),
        sa.PrimaryKeyConstraint("hubs_key", "station_id", name="pk_station_hubs"),
        key_constraint("station_hubs", "hubs_key"),
    )
    op.create_table(
        "hub_pairs",
        key_column("instance_key"),
        key_column("origin_hub"),
        key_column("destination_hub"),
        sa.Column("demand", sa.Double, nullable=False),
        sa.Column("euclid_dist_m", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint(
            "instance_key", "origin_hub", "destination_hub", name="pk_hub_pairs"
        ),
        key_constraint("hub_pairs", "instance_key"),
    )
    op.create_table(
        "route_options",
        key_column("instance_key"),
        key_column("arc_id"),
        key_column("origin_hub"),
        key_column("destination_hub"),
        key_column("mode"),
        sa.Column("total_travel_time_s", sa.Double, nullable=False),
        sa.Column("total_transfer_time_s", sa.Double, nullable=False),
        sa.Column("total_distance_m", sa.Double, nullable=False),
        sa.Column("legs", postgresql.JSONB, nullable=False),
        sa.Column("geometry", postgresql.JSONB, nullable=False),
        # Filled from the package's parser by a later story: null until then.
        sa.Column("bike_legs", sa.Integer, nullable=True),
        sa.Column("bike_time_min", sa.Double, nullable=True),
        sa.Column("pt_time_min", sa.Double, nullable=True),
        sa.Column("transfer_time_min", sa.Double, nullable=True),
        sa.Column("parking_time_min", sa.Double, nullable=True),
        sa.Column("car_cost_chf", sa.Double, nullable=True),
        sa.PrimaryKeyConstraint("instance_key", "arc_id", name="pk_route_options"),
        key_constraint("route_options", "instance_key"),
        sa.CheckConstraint(
            "mode IN ('pt_bike', 'pt_only', 'car')", name=op.f("ck_route_options_mode")
        ),
    )
    op.create_table(
        "station_bikes",
        key_column("instance_key"),
        key_column("station_id"),
        sa.Column("capacity", sa.Double, nullable=False),
        sa.Column("inventory_start", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint("instance_key", "station_id", name="pk_station_bikes"),
        key_constraint("station_bikes", "instance_key"),
    )
    op.create_table(
        "option_station_deltas",
        key_column("instance_key"),
        key_column("arc_id"),
        key_column("station_id"),
        sa.Column("delta", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint(
            "instance_key", "arc_id", "station_id", name="pk_option_station_deltas"
        ),
        key_constraint("option_station_deltas", "instance_key"),
    )
    op.create_table(
        "route_failures",
        sa.Column("id", sa.BigInteger, sa.Identity(), nullable=False),
        key_column("run_id"),
        sa.Column("run_step_id", sa.BigInteger, nullable=False),
        sa.Column("instance_period_id", sa.Text, nullable=True),
        key_column("origin_hub"),
        key_column("destination_hub"),
        key_column("query"),
        key_column("kind"),
        key_column("message"),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_route_failures"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_route_failures_run_id_runs", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id"],
            ["run_steps.id"],
            name="fk_route_failures_run_step_id_run_steps",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instance_period_id"],
            ["instance_periods.id"],
            name="fk_route_failures_instance_period_id_instance_periods",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("query IN ('pt_bike', 'car')", name=op.f("ck_route_failures_query")),
        sa.CheckConstraint(
            "kind IN ('technical', 'no_route')", name=op.f("ck_route_failures_kind")
        ),
        sa.CheckConstraint("attempts >= 1", name=op.f("ck_route_failures_attempts")),
    )
    op.create_index("ix_route_failures_run_id", "route_failures", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_route_failures_run_id", table_name="route_failures")
    op.drop_table("route_failures")
    for table in READ_MODEL_TABLES:
        op.drop_table(table)
    for column in ("ingested_at", "counts", "reported_counts", "run_id"):
        op.drop_column("artifacts", column)
