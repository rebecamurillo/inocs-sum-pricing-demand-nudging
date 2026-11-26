"""City data sets: an immutable import of a city's timetable and bike stations.

Revision ID: 8e4b2f6a1c97
Revises: 5d2a9c4e7b13
Create Date: 2026-11-26 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8e4b2f6a1c97"
down_revision: str | None = "5d2a9c4e7b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "city_datasets",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("gtfs_file", sa.Text, nullable=False),
        sa.Column("gtfs_sha256", sa.Text, nullable=False),
        sa.Column("gtfs_source_sha256", sa.Text, nullable=False),
        sa.Column("gtfs_valid_from", sa.Date, nullable=False),
        sa.Column("gtfs_valid_to", sa.Date, nullable=False),
        sa.Column("gtfs_timezone", sa.Text, nullable=False),
        sa.Column("gbfs_file", sa.Text, nullable=False),
        sa.Column("gbfs_sha256", sa.Text, nullable=False),
        sa.Column("gbfs_source_url", sa.Text, nullable=False),
        sa.Column("gbfs_fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_area", postgresql.JSONB, nullable=False),
        sa.Column("preset", postgresql.JSONB, nullable=False),
        sa.Column("routing_date", sa.Date, nullable=False),
        sa.Column("routing_time", sa.Time, nullable=False),
        sa.Column("arrive_by", sa.Boolean, nullable=False),
        sa.Column("routing_date_provisional", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_city_datasets"),
        sa.CheckConstraint(
            "gtfs_valid_from <= gtfs_valid_to", name=op.f("ck_city_datasets_gtfs_validity")
        ),
    )


def downgrade() -> None:
    op.drop_table("city_datasets")
