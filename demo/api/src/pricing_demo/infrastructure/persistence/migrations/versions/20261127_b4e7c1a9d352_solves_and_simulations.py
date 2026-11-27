"""The solves of the pricing model with their rows, the traveller simulations with their child
rows, the links of a pricing version to its simulations, and the rule each worker uses.

The `pricing_model` step stores an artefact too, so the artefacts' step check accepts it.

Revision ID: b4e7c1a9d352
Revises: f2c6a9d4b871
Create Date: 2026-11-27 21:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b4e7c1a9d352"
down_revision: str | None = "f2c6a9d4b871"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The values are written out here, not imported from tables.py: a merged migration must keep
# creating the same schema when the application's tables change later.
BUILD_STEPS = "step IN ('area', 'hubs', 'routes', 'travellers_and_bikes')"
ARTIFACT_STEPS = "step IN ('area', 'hubs', 'routes', 'travellers_and_bikes', 'pricing_model')"
SOLVE_ROW_TYPES = "type IN ('PT+Bike', 'PT-Only', 'Car')"
PRICE_SCHEMES = "price_scheme IN ('model_prices', 'flat')"
ADAPTERS = "adapter IN ('domain', 'package')"
MODES = "mode IN ('pt_bike', 'pt_only', 'car')"


def _cascade_to_artifact(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["solve_key"],
        ["artifacts.input_key"],
        name=f"fk_{table}_solve_key_artifacts",
        ondelete="CASCADE",
    )


def _cascade_to_simulation(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["simulation_key"],
        ["simulations.simulation_key"],
        name=f"fk_{table}_simulation_key_simulations",
        ondelete="CASCADE",
    )


def upgrade() -> None:
    op.drop_constraint(op.f("ck_artifacts_step"), "artifacts", type_="check")
    op.create_check_constraint(op.f("ck_artifacts_step"), "artifacts", ARTIFACT_STEPS)
    op.create_table(
        "solves",
        sa.Column("id", sa.Text, nullable=False),
        sa.Column("pricing_version_id", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text, nullable=False),
        sa.Column("input_key", sa.Text, nullable=False),
        sa.Column("solver_status", sa.Integer, nullable=False),
        sa.Column("solver_status_name", sa.Text, nullable=False),
        sa.Column("objective_value", sa.Double, nullable=True),
        sa.Column("gap_pct", sa.Double, nullable=True),
        sa.Column("solution_time_s", sa.Double, nullable=True),
        sa.Column("sol_count", sa.Integer, nullable=False),
        sa.Column("time_limit_reached", sa.Boolean, nullable=False),
        sa.Column("gurobi_version", sa.Text, nullable=False),
        sa.Column("licence_kind", sa.Text, nullable=False),
        sa.Column("solver_parameters", postgresql.JSONB, nullable=False),
        sa.Column("package_fingerprint", sa.Text, nullable=False),
        sa.Column("demonstrator_version", sa.Text, nullable=False),
        sa.Column("dependency_lock_sha256", sa.Text, nullable=False),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_solves"),
        sa.UniqueConstraint("pricing_version_id", "period_id", name="uq_solves_pricing_version_id"),
        sa.ForeignKeyConstraint(
            ["pricing_version_id"],
            ["pricing_versions.id"],
            name="fk_solves_pricing_version_id_pricing_versions",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"], ["instance_periods.id"], name="fk_solves_period_id_instance_periods"
        ),
        sa.ForeignKeyConstraint(
            ["input_key"], ["artifacts.input_key"], name="fk_solves_input_key_artifacts"
        ),
    )
    op.create_table(
        "solve_rows",
        sa.Column("solve_key", sa.Text, nullable=False),
        sa.Column("arc_id", sa.Text, nullable=False),
        sa.Column("origin_hub", sa.Text, nullable=False),
        sa.Column("destination_hub", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("nu", sa.Double, nullable=False),
        sa.Column("flow", sa.Double, nullable=False),
        sa.Column("bike_price", sa.Double, nullable=True),
        sa.Column("total_price", sa.Double, nullable=True),
        sa.Column("z_value", sa.Double, nullable=True),
        sa.Column("relaxation_difference", sa.Double, nullable=True),
        sa.PrimaryKeyConstraint("solve_key", "arc_id", name="pk_solve_rows"),
        _cascade_to_artifact("solve_rows"),
        sa.CheckConstraint(SOLVE_ROW_TYPES, name=op.f("ck_solve_rows_type")),
    )
    op.create_table(
        "solve_ods",
        sa.Column("solve_key", sa.Text, nullable=False),
        sa.Column("origin_hub", sa.Text, nullable=False),
        sa.Column("destination_hub", sa.Text, nullable=False),
        sa.Column("gamma", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint("solve_key", "origin_hub", "destination_hub", name="pk_solve_ods"),
        _cascade_to_artifact("solve_ods"),
    )
    op.create_table(
        "simulations",
        sa.Column("simulation_key", sa.Text, nullable=False),
        sa.Column("instance_key", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text, nullable=False),
        sa.Column("rule_id", sa.Text, nullable=False),
        sa.Column("rule_version", sa.Integer, nullable=False),
        sa.Column("rule_parameters", postgresql.JSONB, nullable=False),
        sa.Column("price_scheme", sa.Text, nullable=False),
        sa.Column("solve_key", sa.Text, nullable=True),
        sa.Column("flat_price_kind", sa.Text, nullable=True),
        sa.Column("flat_price_amount_chf", sa.Double, nullable=True),
        sa.Column("pt_fare_chf", sa.Double, nullable=False),
        sa.Column("car_parking_fee_chf", sa.Double, nullable=False),
        sa.Column("travellers", sa.Integer, nullable=False),
        sa.Column("displaced", sa.Integer, nullable=False),
        sa.Column("unserved", sa.Integer, nullable=False),
        sa.Column("bike_rides", sa.Integer, nullable=False),
        sa.Column("bike_revenue_chf", sa.Double, nullable=False),
        sa.Column("stations_empty", sa.Integer, nullable=False),
        sa.Column("stations_full", sa.Integer, nullable=False),
        sa.Column("adapter", sa.Text, nullable=False),
        sa.Column("package_fingerprint", sa.Text, nullable=True),
        sa.Column("demonstrator_version", sa.Text, nullable=False),
        sa.Column("duration_s", sa.Double, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("simulation_key", name="pk_simulations"),
        sa.CheckConstraint(PRICE_SCHEMES, name=op.f("ck_simulations_price_scheme")),
        sa.CheckConstraint(ADAPTERS, name=op.f("ck_simulations_adapter")),
    )
    op.create_table(
        "simulation_modes",
        sa.Column("simulation_key", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("travellers", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("simulation_key", "mode", name="pk_simulation_modes"),
        _cascade_to_simulation("simulation_modes"),
        sa.CheckConstraint(MODES, name=op.f("ck_simulation_modes_mode")),
    )
    op.create_table(
        "simulation_choices",
        sa.Column("simulation_key", sa.Text, nullable=False),
        sa.Column("origin_hub", sa.Text, nullable=False),
        sa.Column("destination_hub", sa.Text, nullable=False),
        sa.Column("arc_id", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=False),
        sa.Column("travellers", sa.Integer, nullable=False),
        sa.Column("price_chf", sa.Double, nullable=False),
        sa.Column("displaced", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint(
            "simulation_key",
            "origin_hub",
            "destination_hub",
            "arc_id",
            name="pk_simulation_choices",
        ),
        _cascade_to_simulation("simulation_choices"),
        sa.CheckConstraint(MODES, name=op.f("ck_simulation_choices_mode")),
    )
    op.create_table(
        "simulation_pairs",
        sa.Column("simulation_key", sa.Text, nullable=False),
        sa.Column("origin_hub", sa.Text, nullable=False),
        sa.Column("destination_hub", sa.Text, nullable=False),
        sa.Column("unserved", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint(
            "simulation_key", "origin_hub", "destination_hub", name="pk_simulation_pairs"
        ),
        _cascade_to_simulation("simulation_pairs"),
    )
    op.create_table(
        "simulation_stations",
        sa.Column("simulation_key", sa.Text, nullable=False),
        sa.Column("station_id", sa.Text, nullable=False),
        sa.Column("bikes_end", sa.Double, nullable=False),
        sa.Column("empty", sa.Boolean, nullable=False),
        sa.Column("full", sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint("simulation_key", "station_id", name="pk_simulation_stations"),
        _cascade_to_simulation("simulation_stations"),
    )
    op.create_table(
        "pricing_version_simulations",
        sa.Column("pricing_version_id", sa.Text, nullable=False),
        sa.Column("period_id", sa.Text, nullable=False),
        sa.Column("price_scheme", sa.Text, nullable=False),
        sa.Column("rule_id", sa.Text, nullable=False),
        sa.Column("rule_version", sa.Integer, nullable=False),
        sa.Column("simulation_key", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "pricing_version_id",
            "period_id",
            "price_scheme",
            "rule_id",
            "rule_version",
            name="pk_pricing_version_simulations",
        ),
        sa.ForeignKeyConstraint(
            ["pricing_version_id"],
            ["pricing_versions.id"],
            name="fk_pvs_pricing_version_id_pricing_versions",
        ),
        sa.ForeignKeyConstraint(
            ["period_id"],
            ["instance_periods.id"],
            name="fk_pricing_version_simulations_period_id_instance_periods",
        ),
        sa.ForeignKeyConstraint(
            ["simulation_key"],
            ["simulations.simulation_key"],
            name="fk_pricing_version_simulations_simulation_key_simulations",
        ),
        sa.CheckConstraint(PRICE_SCHEMES, name=op.f("ck_pricing_version_simulations_price_scheme")),
    )
    op.add_column("workers", sa.Column("simulation_rule", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("workers", "simulation_rule")
    op.drop_table("pricing_version_simulations")
    op.drop_table("simulation_stations")
    op.drop_table("simulation_pairs")
    op.drop_table("simulation_choices")
    op.drop_table("simulation_modes")
    op.drop_table("simulations")
    op.drop_table("solve_ods")
    op.drop_table("solve_rows")
    op.drop_table("solves")
    op.execute("DELETE FROM artifacts WHERE step = 'pricing_model'")
    op.drop_constraint(op.f("ck_artifacts_step"), "artifacts", type_="check")
    op.create_check_constraint(op.f("ck_artifacts_step"), "artifacts", BUILD_STEPS)
