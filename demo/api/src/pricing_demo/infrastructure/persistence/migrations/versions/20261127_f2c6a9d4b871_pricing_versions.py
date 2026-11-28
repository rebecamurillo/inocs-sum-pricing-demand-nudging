"""Pricing versions and their periods, the immutability trigger on their goals, the next
letter of each instance version, and the foreign key from the runs' pricing subject.

Revision ID: f2c6a9d4b871
Revises: d5b8e2a7c314
Create Date: 2026-11-27 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c6a9d4b871"
down_revision: str | None = "d5b8e2a7c314"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values are written out here, not imported from tables.py: a merged migration must keep
# creating the same schema when the application's tables change later.
STATUSES = "status IN ('draft', 'sealed')"
FLAT_PRICE_KINDS = "flat_price_kind IN ('per_ride')"
GOALS = (
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "pt_fare_chf",
    "car_parking_fee_chf",
    "max_displayed_options",
    "flat_price_per_ride_chf",
)
SEALED_FUNCTION = "pricing_versions_sealed_goals"
SEALED_TRIGGER = "pricing_versions_sealed_goals"


def sealed_function_body() -> str:
    changed = " OR ".join(f"NEW.{name} IS DISTINCT FROM OLD.{name}" for name in GOALS)
    return f"""
        CREATE FUNCTION {SEALED_FUNCTION}() RETURNS trigger AS $$
        BEGIN
            IF OLD.status = 'sealed' AND ({changed}) THEN
                RAISE EXCEPTION 'The goals of the saved pricing version % cannot change', OLD.id
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """


def upgrade() -> None:
    op.add_column(
        "instance_versions",
        sa.Column("next_pricing_letter", sa.Integer, nullable=False, server_default=sa.text("0")),
    )
    op.create_table(
        "pricing_versions",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("instance_version_id", sa.Text, nullable=False),
        sa.Column("letter", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("based_on_id", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        *(sa.Column(name, sa.Double, nullable=False) for name in GOALS[:7]),
        sa.Column("flat_price_kind", sa.Text, nullable=False),
        sa.Column("flat_price_per_ride_chf", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pricing_versions"),
        sa.UniqueConstraint(
            "instance_version_id", "letter", name="uq_pricing_versions_instance_version_id"
        ),
        sa.ForeignKeyConstraint(
            ["instance_version_id"],
            ["instance_versions.id"],
            name="fk_pricing_versions_instance_version_id_instance_versions",
        ),
        sa.ForeignKeyConstraint(
            ["based_on_id"],
            ["pricing_versions.id"],
            name="fk_pricing_versions_based_on_id_pricing_versions",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(STATUSES, name=op.f("ck_pricing_versions_status")),
        sa.CheckConstraint(FLAT_PRICE_KINDS, name=op.f("ck_pricing_versions_flat_price_kind")),
    )
    op.create_table(
        "pricing_version_periods",
        sa.Column("pricing_version_id", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint(
            "pricing_version_id", "period_id", name="pk_pricing_version_periods"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_version_id"],
            ["pricing_versions.id"],
            name="fk_pricing_version_periods_pricing_version_id_pricing_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["instance_periods.id"],
            name="fk_pricing_version_periods_period_id_instance_periods",
        ),
    )
    op.execute(sealed_function_body())
    op.execute(
        f"CREATE TRIGGER {SEALED_TRIGGER} BEFORE UPDATE ON pricing_versions "
        f"FOR EACH ROW EXECUTE FUNCTION {SEALED_FUNCTION}()"
    )
    op.create_foreign_key(
        "fk_runs_pricing_version_id_pricing_versions",
        "runs",
        "pricing_versions",
        ["pricing_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_runs_pricing_version_id_pricing_versions", "runs", type_="foreignkey")
    op.execute(f"DROP TRIGGER {SEALED_TRIGGER} ON pricing_versions")
    op.execute(f"DROP FUNCTION {SEALED_FUNCTION}()")
    op.drop_table("pricing_version_periods")
    op.drop_table("pricing_versions")
    op.drop_column("instance_versions", "next_pricing_letter")
