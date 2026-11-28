"""The worker's component reports and the fake adapters' settings.

Revision ID: 5d2a9c4e7b13
Revises: 3b8e5d1f9a62
Create Date: 2026-11-26 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5d2a9c4e7b13"
down_revision: str | None = "3b8e5d1f9a62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPONENT_STATES = ("available", "limited", "unavailable")


def one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


def upgrade() -> None:
    op.create_table(
        "component_reports",
        sa.Column("component", sa.Text, nullable=False),
        sa.Column("state", sa.Text, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column(
            "details",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("worker_id", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("component", name="pk_component_reports"),
        sa.CheckConstraint(
            one_of("state", COMPONENT_STATES), name=op.f("ck_component_reports_state")
        ),
    )
    op.create_table(
        "fake_settings",
        sa.Column("id", sa.Integer, autoincrement=False, nullable=False),
        sa.Column("settings", postgresql.JSONB, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fake_settings"),
        sa.CheckConstraint("id = 1", name=op.f("ck_fake_settings_single_row")),
    )


def downgrade() -> None:
    op.drop_table("fake_settings")
    op.drop_table("component_reports")
