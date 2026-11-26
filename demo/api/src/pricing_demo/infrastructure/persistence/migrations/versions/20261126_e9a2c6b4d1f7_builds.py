"""The artefacts a build stores under input keys, and the link of each instance version to the
artefact of each of its steps.

Revision ID: e9a2c6b4d1f7
Revises: c4f8a21d7e53
Create Date: 2026-11-26 23:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9a2c6b4d1f7"
down_revision: str | None = "c4f8a21d7e53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values are written out here, not imported from tables.py: a merged migration must keep
# creating the same schema when the application's tables change later.
BUILD_STEPS = "step IN ('area', 'hubs', 'routes', 'travellers_and_bikes')"


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("input_key", sa.Text, nullable=False),
        sa.Column("step", sa.Text, nullable=False),
        sa.Column("inputs", postgresql.JSONB, nullable=False),
        sa.Column("files", postgresql.JSONB, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("package_fingerprint", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("input_key", name="pk_artifacts"),
        sa.ForeignKeyConstraint(
            ["package_fingerprint"],
            ["package_fingerprints.fingerprint"],
            name="fk_artifacts_package_fingerprint_package_fingerprints",
        ),
        sa.CheckConstraint(BUILD_STEPS, name=op.f("ck_artifacts_step")),
    )
    # The period of steps 1 and 2 is null, and a primary key cannot hold a null: the unique
    # constraint treats two nulls as equal, so a step has one artefact per version and period.
    op.create_table(
        "instance_version_steps",
        sa.Column("id", sa.BigInteger, sa.Identity(), nullable=False),
        sa.Column("instance_version_id", sa.Text, nullable=False),
        sa.Column("step", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text, nullable=True),
        sa.Column("input_key", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_instance_version_steps"),
        sa.UniqueConstraint(
            "instance_version_id",
            "step",
            "period_id",
            name="uq_instance_version_steps_instance_version_id",
            postgresql_nulls_not_distinct=True,
        ),
        sa.ForeignKeyConstraint(
            ["instance_version_id"],
            ["instance_versions.id"],
            name="fk_instance_version_steps_instance_version_id_instance_versions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["instance_periods.id"],
            name="fk_instance_version_steps_period_id_instance_periods",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["input_key"],
            ["artifacts.input_key"],
            name="fk_instance_version_steps_input_key_artifacts",
        ),
        sa.CheckConstraint(BUILD_STEPS, name=op.f("ck_instance_version_steps_step")),
    )


def downgrade() -> None:
    op.drop_table("instance_version_steps")
    op.drop_table("artifacts")
