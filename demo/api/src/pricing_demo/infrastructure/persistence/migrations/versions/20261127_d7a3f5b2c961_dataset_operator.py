"""The timetable operator of a city data set: the agency names of its `agency.txt`.

Revision ID: d7a3f5b2c961
Revises: c9d4e1b7a538
Create Date: 2026-11-27 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3f5b2c961"
down_revision: str | None = "c9d4e1b7a538"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("city_datasets", sa.Column("gtfs_operator", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("city_datasets", "gtfs_operator")
