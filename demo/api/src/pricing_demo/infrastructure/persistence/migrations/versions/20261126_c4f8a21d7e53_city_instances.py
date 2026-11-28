"""City instances, their versions and periods, the package fingerprints, and the foreign keys
from the runs' subject columns.

Revision ID: c4f8a21d7e53
Revises: b7d3a05c4e18
Create Date: 2026-11-26 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4f8a21d7e53"
down_revision: str | None = "b7d3a05c4e18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values are written out here, not imported from tables.py: a merged migration must keep
# creating the same schema when the application's tables change later.
VERSION_STATUSES = "status IN ('draft', 'sealed')"
# Every parameter is a double: a value is stored as sent, so a seed of 1.5 is kept and
# reported as a broken rule instead of being rounded by the database.
PARAMETERS = (
    "center_lat",
    "center_lon",
    "radius_m",
    "clustering_threshold_m",
    "clustering_buffer_m",
    "min_od_distance_m",
    "seed",
    "fixed_capacity",
    "min_demand",
    "max_demand",
    "min_inventory_pct",
    "max_inventory_pct",
    "min_park_time_min",
    "max_park_time_min",
)
SEALED_FUNCTION = "instance_versions_sealed_parameters"
SEALED_TRIGGER = "instance_versions_sealed_parameters"


def sealed_function_body() -> str:
    changed = " OR ".join(f"NEW.{name} IS DISTINCT FROM OLD.{name}" for name in PARAMETERS)
    return f"""
        CREATE FUNCTION {SEALED_FUNCTION}() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'sealed' AND ({changed}) THEN
                RAISE EXCEPTION 'The parameters of the saved version % cannot change', OLD.id
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """


def upgrade() -> None:
    op.create_table(
        "package_fingerprints",
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("git_commit", sa.Text, nullable=False),
        sa.Column("git_dirty", sa.Boolean, nullable=False),
        sa.Column("defaults", postgresql.JSONB, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("fingerprint", name="pk_package_fingerprints"),
    )
    # No foreign key: the e2e reset truncates both tables independently.
    op.add_column("workers", sa.Column("package_fingerprint", sa.Text, nullable=True))
    op.create_table(
        "city_instances",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("dataset_id", sa.Text, nullable=False),
        sa.Column("next_number", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_city_instances"),
        sa.UniqueConstraint("name", name="uq_city_instances_name"),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["city_datasets.id"], name="fk_city_instances_dataset_id_city_datasets"
        ),
    )
    op.create_table(
        "instance_versions",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("instance_id", sa.Text, nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("based_on_id", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        *(sa.Column(name, sa.Double, nullable=False) for name in PARAMETERS),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_instance_versions"),
        sa.UniqueConstraint("instance_id", "number", name="uq_instance_versions_instance_id"),
        sa.ForeignKeyConstraint(
            ["instance_id"],
            ["city_instances.id"],
            name="fk_instance_versions_instance_id_city_instances",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["based_on_id"],
            ["instance_versions.id"],
            name="fk_instance_versions_based_on_id_instance_versions",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(VERSION_STATUSES, name=op.f("ck_instance_versions_status")),
    )
    op.create_index(
        "uq_instance_versions_one_draft",
        "instance_versions",
        ["instance_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft'"),
    )
    op.create_table(
        "instance_periods",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("instance_version_id", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("weekday", sa.Integer, nullable=False),
        sa.Column("start_time", sa.Time, nullable=False),
        sa.Column("end_time", sa.Time, nullable=False),
        sa.Column("routing_date", sa.Date, nullable=False),
        sa.Column("routing_time", sa.Time, nullable=False),
        sa.Column("arrive_by", sa.Boolean, nullable=False),
        sa.Column("routing_date_provisional", sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_instance_periods"),
        sa.UniqueConstraint("instance_version_id", "key", name="uq_instance_periods_version_key"),
        sa.ForeignKeyConstraint(
            ["instance_version_id"],
            ["instance_versions.id"],
            name="fk_instance_periods_instance_version_id_instance_versions",
            ondelete="CASCADE",
        ),
    )
    op.execute(sealed_function_body())
    op.execute(
        f"CREATE TRIGGER {SEALED_TRIGGER} BEFORE UPDATE ON instance_versions "
        f"FOR EACH ROW EXECUTE FUNCTION {SEALED_FUNCTION}()"
    )
    op.create_foreign_key(
        "fk_runs_instance_version_id_instance_versions",
        "runs",
        "instance_versions",
        ["instance_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_run_steps_period_id_instance_periods",
        "run_steps",
        "instance_periods",
        ["period_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_run_steps_period_id_instance_periods", "run_steps", type_="foreignkey")
    op.drop_constraint("fk_runs_instance_version_id_instance_versions", "runs", type_="foreignkey")
    op.execute(f"DROP TRIGGER {SEALED_TRIGGER} ON instance_versions")
    op.execute(f"DROP FUNCTION {SEALED_FUNCTION}()")
    op.drop_table("instance_periods")
    op.drop_index("uq_instance_versions_one_draft", table_name="instance_versions")
    op.drop_table("instance_versions")
    op.drop_table("city_instances")
    op.drop_column("workers", "package_fingerprint")
    op.drop_table("package_fingerprints")
