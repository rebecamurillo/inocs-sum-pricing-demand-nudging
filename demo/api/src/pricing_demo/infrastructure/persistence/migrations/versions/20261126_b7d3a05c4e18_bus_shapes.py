"""Bus shapes: whether the GTFS copy has the bus legs drawn on the streets, why not, and with what.

Revision ID: b7d3a05c4e18
Revises: 8e4b2f6a1c97
Create Date: 2026-11-26 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7d3a05c4e18"
down_revision: str | None = "8e4b2f6a1c97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The server default and the reason only fill the rows imported before this migration.
    op.add_column(
        "city_datasets",
        sa.Column("bus_shapes", sa.Text, nullable=False, server_default="none"),
    )
    op.add_column(
        "city_datasets",
        sa.Column(
            "bus_shapes_reason",
            sa.Text,
            nullable=True,
            server_default="Imported before bus shapes were generated",
        ),
    )
    op.add_column("city_datasets", sa.Column("shape_tool_image", sa.Text, nullable=True))
    op.alter_column("city_datasets", "bus_shapes", server_default=None)
    op.alter_column("city_datasets", "bus_shapes_reason", server_default=None)
    op.create_check_constraint(
        op.f("ck_city_datasets_bus_shapes"),
        "city_datasets",
        "bus_shapes IN ('generated', 'none')",
    )
    op.create_check_constraint(
        op.f("ck_city_datasets_bus_shapes_reason"),
        "city_datasets",
        "(bus_shapes = 'none') = (bus_shapes_reason IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_city_datasets_bus_shapes_reason"), "city_datasets")
    op.drop_constraint(op.f("ck_city_datasets_bus_shapes"), "city_datasets")
    op.drop_column("city_datasets", "shape_tool_image")
    op.drop_column("city_datasets", "bus_shapes_reason")
    op.drop_column("city_datasets", "bus_shapes")
