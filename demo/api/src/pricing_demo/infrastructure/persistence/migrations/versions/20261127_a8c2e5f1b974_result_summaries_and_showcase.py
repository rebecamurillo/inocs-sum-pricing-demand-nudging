"""The numbers of a result, computed once per solve, and the one showcase mark.

Revision ID: a8c2e5f1b974
Revises: e6c1b4a8f209
Create Date: 2026-11-27 23:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8c2e5f1b974"
down_revision: str | None = "e6c1b4a8f209"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "result_summaries",
        sa.Column("solve_key", sa.Text, nullable=False),
        sa.Column("derivation_version", sa.Integer, nullable=False),
        sa.Column("numbers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("package_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("objective_residual", sa.Double, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["solve_key"],
            ["artifacts.input_key"],
            name="fk_result_summaries_solve_key_artifacts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("solve_key", "derivation_version", name="pk_result_summaries"),
    )
    op.create_table(
        "showcase",
        sa.Column("id", sa.Integer, autoincrement=False, nullable=False),
        sa.Column("pricing_version_id", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text, nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_showcase_one_row")),
        sa.ForeignKeyConstraint(
            ["pricing_version_id"],
            ["pricing_versions.id"],
            name="fk_showcase_pricing_version_id_pricing_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"], ["instance_periods.id"], name="fk_showcase_period_id_instance_periods"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_showcase"),
    )


def downgrade() -> None:
    op.drop_table("showcase")
    op.drop_table("result_summaries")
