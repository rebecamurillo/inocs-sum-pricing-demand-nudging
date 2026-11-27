"""The twelve choice-model coefficients of the solver, on the package's fingerprint.

Null on a row recorded before the worker read them; the worker fills it once at its next
start.

Revision ID: e6c1b4a8f209
Revises: b4e7c1a9d352
Create Date: 2026-11-27 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6c1b4a8f209"
down_revision: str | None = "b4e7c1a9d352"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "package_fingerprints",
        sa.Column("choice_coefficients", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("package_fingerprints", "choice_coefficients")
