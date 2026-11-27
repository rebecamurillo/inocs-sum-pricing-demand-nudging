"""The hub pairs the routes step routed, keyed by the routes artefact: the L-1 map draws them
while the last step of a build still runs.

Revision ID: d5b8e2a7c314
Revises: a3d7f1c85b26
Create Date: 2026-11-27 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5b8e2a7c314"
down_revision: str | None = "a3d7f1c85b26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "route_pairs",
        sa.Column("instance_key", sa.Text, nullable=False),
        sa.Column("origin_hub", sa.Text, nullable=False),
        sa.Column("destination_hub", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint(
            "instance_key", "origin_hub", "destination_hub", name="pk_route_pairs"
        ),
        sa.ForeignKeyConstraint(
            ["instance_key"],
            ["artifacts.input_key"],
            name="fk_route_pairs_instance_key_artifacts",
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("route_pairs")
