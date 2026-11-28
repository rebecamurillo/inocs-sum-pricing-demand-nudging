"""The pricing version the kept values of a draft came from.

Revision ID: c9d4e1b7a538
Revises: a8c2e5f1b974
Create Date: 2026-11-27 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9d4e1b7a538"
down_revision: str | None = "a8c2e5f1b974"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Not a goal column: the trigger that freezes the goals of a sealed version ignores it.
    op.add_column(
        "pricing_versions",
        sa.Column(
            "kept_from_id",
            sa.Text,
            sa.ForeignKey("pricing_versions.id", ondelete="SET NULL", name="fk_kept_from"),
        ),
    )


def downgrade() -> None:
    op.drop_column("pricing_versions", "kept_from_id")
