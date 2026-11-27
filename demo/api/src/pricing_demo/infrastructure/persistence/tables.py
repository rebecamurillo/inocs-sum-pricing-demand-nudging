"""The tables of the application, on the shared metadata. Migrations create the same shapes."""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Table,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

from pricing_demo.infrastructure.persistence.metadata import metadata

BUS_SHAPES_STATUSES = ("generated", "none")
RUN_KINDS = ("build", "pricing", "simulation")
RUN_STATES = ("queued", "running", "succeeded", "failed", "cancelled")
STEP_NAMES = (
    "area",
    "hubs",
    "routes",
    "travellers_and_bikes",
    "pricing_model",
    "traveller_simulation",
)
BUILD_STEP_NAMES = ("area", "hubs", "routes", "travellers_and_bikes")
ARTIFACT_STEP_NAMES = (*BUILD_STEP_NAMES, "pricing_model")
SOLVE_ROW_TYPES = ("PT+Bike", "PT-Only", "Car")
PRICE_SCHEMES = ("model_prices", "flat")
SIMULATION_ADAPTERS = ("domain", "package")
ROUTE_MODES = ("pt_bike", "pt_only", "car")
VERSION_STATUSES = ("draft", "sealed")
PRICING_GOAL_COLUMNS = (
    "cost_bike_chf",
    "lowest_price_chf",
    "ridership_weight",
    "station_balance_weight",
    "pt_fare_chf",
    "car_parking_fee_chf",
    "max_displayed_options",
)
FLAT_PRICE_KINDS = ("per_ride",)
PARAMETER_COLUMNS = (
    "center_lat",
    "center_lon",
    "radius_m",
    "clustering_threshold_m",
    "clustering_buffer_m",
    "min_od_distance_m",
    "seed",
    "fixed_capacity",
    "min_demand",
    "max_demand",
    "min_inventory_pct",
    "max_inventory_pct",
    "min_park_time_min",
    "max_park_time_min",
)
STEP_STATES = ("pending", "running", "done", "kept", "failed", "cancelled")

KIND_SUBJECT_CHECK = (
    "(kind = 'build' AND instance_version_id IS NOT NULL AND pricing_version_id IS NULL)"
    " OR (kind IN ('pricing', 'simulation') AND pricing_version_id IS NOT NULL"
    " AND instance_version_id IS NULL)"
)
ACTIVE_RUN_PREDICATE = "state IN ('queued', 'running')"


def one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


workers = Table(
    "workers",
    metadata,
    Column("id", Text, primary_key=True),
    Column("host", Text, nullable=False),
    Column("pid", Integer, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
    # No foreign key: the e2e reset truncates both tables independently.
    Column("package_fingerprint", Text),
    # The id, version and parameters of the traveller simulation rule the worker uses.
    Column("simulation_rule", JSONB),
)

runs = Table(
    "runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("instance_version_id", Text, ForeignKey("instance_versions.id")),
    Column("pricing_version_id", Text, ForeignKey("pricing_versions.id")),
    Column("state", Text, nullable=False),
    Column("attempt", Integer, nullable=False, server_default=text("1")),
    Column("queued_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("heartbeat_at", DateTime(timezone=True)),
    Column("worker_id", Text, ForeignKey("workers.id")),
    Column("child_pid", Integer),
    Column("cancel_requested_at", DateTime(timezone=True)),
    Column("failed_step", Text),
    Column("failure_code", Text),
    Column("failure_reason", Text),
    Column("failure_pct", Double),
    CheckConstraint(one_of("kind", RUN_KINDS), name="kind"),
    CheckConstraint(one_of("state", RUN_STATES), name="state"),
    CheckConstraint(KIND_SUBJECT_CHECK, name="kind_subject"),
    Index(
        "uq_runs_active_subject",
        text("coalesce(instance_version_id, pricing_version_id)"),
        unique=True,
        postgresql_where=text(ACTIVE_RUN_PREDICATE),
    ),
)

run_steps = Table(
    "run_steps",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("run_id", Text, ForeignKey("runs.id"), nullable=False),
    Column("position", Integer, nullable=False),
    Column("step", Text, nullable=False),
    Column("period_id", Text, ForeignKey("instance_periods.id")),
    Column("state", Text, nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("counts", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("progress_done", Integer),
    Column("progress_total", Integer),
    Column("reason", Text),
    Column("input_key", Text),
    Column("peak_rss_bytes", BigInteger),
    Column("log_excerpt", Text),
    UniqueConstraint("run_id", "position", name="uq_run_steps_run_id_position"),
    CheckConstraint(one_of("step", STEP_NAMES), name="step"),
    CheckConstraint(one_of("state", STEP_STATES), name="state"),
)

COMPONENT_STATES = ("available", "limited", "unavailable")

# `worker_id` has no foreign key: the e2e reset truncates `workers` and the worker must still
# be able to write its reports. A report is fresh when the `workers` row it names beats.
component_reports = Table(
    "component_reports",
    metadata,
    Column("component", Text, primary_key=True),
    Column("state", Text, nullable=False),
    Column("reason", Text),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("reported_at", DateTime(timezone=True), nullable=False),
    Column("worker_id", Text, nullable=False),
    CheckConstraint(one_of("state", COMPONENT_STATES), name="state"),
)

# One row, written by the test-control routes; always empty with real adapters.
fake_settings = Table(
    "fake_settings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column("settings", JSONB, nullable=False),
    CheckConstraint("id = 1", name="single_row"),
)

# An immutable import of a city's timetable and bike stations. `available_area` is a GeoJSON
# polygon, `preset` is `{centre_lat, centre_lon, radius_m}`. Files are paths relative to the
# worker's data directory.
city_datasets = Table(
    "city_datasets",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("gtfs_file", Text, nullable=False),
    Column("gtfs_sha256", Text, nullable=False),
    Column("gtfs_source_sha256", Text, nullable=False),
    Column("gtfs_valid_from", Date, nullable=False),
    Column("gtfs_valid_to", Date, nullable=False),
    Column("gtfs_timezone", Text, nullable=False),
    Column("gbfs_file", Text, nullable=False),
    Column("gbfs_sha256", Text, nullable=False),
    Column("gbfs_source_url", Text, nullable=False),
    Column("gbfs_fetched_at", DateTime(timezone=True), nullable=False),
    Column("available_area", JSONB, nullable=False),
    Column("preset", JSONB, nullable=False),
    Column("routing_date", Date, nullable=False),
    Column("routing_time", Time, nullable=False),
    Column("arrive_by", Boolean, nullable=False),
    Column("routing_date_provisional", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # `generated` when the GTFS copy holds shapes of the bus trips, else `none` with the reason.
    # Both are set on every row; only rows imported before bus shapes existed lack the image.
    Column("bus_shapes", Text, nullable=False),
    Column("bus_shapes_reason", Text),
    Column("shape_tool_image", Text),
    CheckConstraint("gtfs_valid_from <= gtfs_valid_to", name="gtfs_validity"),
    CheckConstraint(one_of("bus_shapes", BUS_SHAPES_STATUSES), name="bus_shapes"),
    CheckConstraint(
        "(bus_shapes = 'none') = (bus_shapes_reason IS NOT NULL)", name="bus_shapes_reason"
    ),
)

# What the worker found out about the pricing package it runs: `defaults` holds the dataclass
# defaults of `PipelineConfig`, `InstanceParams` and `OptimizerParams`, `choice_coefficients` the
# twelve choice-model constants of the solver (null on a row recorded before they were read).
package_fingerprints = Table(
    "package_fingerprints",
    metadata,
    Column("fingerprint", Text, primary_key=True),
    Column("version", Text, nullable=False),
    Column("git_commit", Text, nullable=False),
    Column("git_dirty", Boolean, nullable=False),
    Column("defaults", JSONB, nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    Column("choice_coefficients", JSONB),
)

city_instances = Table(
    "city_instances",
    metadata,
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("dataset_id", Text, ForeignKey("city_datasets.id"), nullable=False),
    Column("next_number", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("name", name="uq_city_instances_name"),
)

# The parameters are doubles: a value is stored as sent. The trigger that refuses an UPDATE of
# a parameter once `status = 'sealed'` exists in the migration only.
instance_versions = Table(
    "instance_versions",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "instance_id",
        Text,
        ForeignKey("city_instances.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("number", Integer, nullable=False),
    Column("based_on_id", Text, ForeignKey("instance_versions.id", ondelete="SET NULL")),
    Column("status", Text, nullable=False),
    *(Column(name, Double, nullable=False) for name in PARAMETER_COLUMNS),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("sealed_at", DateTime(timezone=True)),
    # The letter the next pricing version takes (0 = A); never decreased, so letters are not
    # reused after a deletion.
    Column("next_pricing_letter", Integer, nullable=False, server_default=text("0")),
    UniqueConstraint("instance_id", "number", name="uq_instance_versions_instance_id"),
    CheckConstraint(one_of("status", VERSION_STATUSES), name="status"),
    Index(
        "uq_instance_versions_one_draft",
        "instance_id",
        unique=True,
        postgresql_where=text("status = 'draft'"),
    ),
)

instance_periods = Table(
    "instance_periods",
    metadata,
    Column("id", Text, primary_key=True),
    Column(
        "instance_version_id",
        Text,
        ForeignKey("instance_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("key", Text, nullable=False),
    Column("label", Text, nullable=False),
    Column("weekday", Integer, nullable=False),
    Column("start_time", Time, nullable=False),
    Column("end_time", Time, nullable=False),
    Column("routing_date", Date, nullable=False),
    Column("routing_time", Time, nullable=False),
    Column("arrive_by", Boolean, nullable=False),
    Column("routing_date_provisional", Boolean, nullable=False),
    UniqueConstraint("instance_version_id", "key", name="uq_instance_periods_version_key"),
)

# The goals are doubles: a value is stored as sent. The trigger that refuses an UPDATE of a goal
# once `status = 'sealed'` exists in the migration only.
pricing_versions = Table(
    "pricing_versions",
    metadata,
    Column("id", Text, primary_key=True),
    Column("instance_version_id", Text, ForeignKey("instance_versions.id"), nullable=False),
    Column("letter", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("based_on_id", Text, ForeignKey("pricing_versions.id", ondelete="SET NULL")),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("sealed_at", DateTime(timezone=True)),
    *(Column(name, Double, nullable=False) for name in PRICING_GOAL_COLUMNS),
    Column("flat_price_kind", Text, nullable=False),
    Column("flat_price_per_ride_chf", Double, nullable=False),
    UniqueConstraint(
        "instance_version_id", "letter", name="uq_pricing_versions_instance_version_id"
    ),
    CheckConstraint(one_of("status", VERSION_STATUSES), name="status"),
    CheckConstraint(one_of("flat_price_kind", FLAT_PRICE_KINDS), name="flat_price_kind"),
)

pricing_version_periods = Table(
    "pricing_version_periods",
    metadata,
    Column(
        "pricing_version_id",
        Text,
        ForeignKey("pricing_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("period_id", Text, ForeignKey("instance_periods.id"), primary_key=True),
)

# The outputs of one build step, named by its input key. `inputs` is the canonical JSON the key
# hashes, `files` lists each file's name, sha256 and size, `path` is the folder relative to the
# worker's data directory.
artifacts = Table(
    "artifacts",
    metadata,
    Column("input_key", Text, primary_key=True),
    Column("step", Text, nullable=False),
    Column("inputs", JSONB, nullable=False),
    Column("files", JSONB, nullable=False),
    Column("path", Text, nullable=False),
    Column(
        "package_fingerprint",
        Text,
        ForeignKey("package_fingerprints.fingerprint"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    # The run that produced it and the counts that run's step reported; `counts` and
    # `ingested_at` are written by the ingestion, in the transaction that stores the rows.
    Column("run_id", Text, ForeignKey("runs.id", ondelete="SET NULL")),
    Column("reported_counts", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("counts", JSONB),
    Column("ingested_at", DateTime(timezone=True)),
    CheckConstraint(one_of("step", ARTIFACT_STEP_NAMES), name="step"),
)

# The artefact of each step of a version. The period is null for the steps that have none, so
# the key is a unique constraint that treats two nulls as equal.
instance_version_steps = Table(
    "instance_version_steps",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column(
        "instance_version_id",
        Text,
        ForeignKey("instance_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("step", Text, nullable=False),
    Column("period_id", Text, ForeignKey("instance_periods.id", ondelete="CASCADE")),
    Column("input_key", Text, ForeignKey("artifacts.input_key"), nullable=False),
    UniqueConstraint(
        "instance_version_id",
        "step",
        "period_id",
        name="uq_instance_version_steps_instance_version_id",
        postgresql_nulls_not_distinct=True,
    ),
    CheckConstraint(one_of("step", BUILD_STEP_NAMES), name="step"),
)


def _artifact_key(name: str) -> Column[str]:
    return Column(name, Text, ForeignKey("artifacts.input_key", ondelete="CASCADE"), nullable=False)


# The read model: every row names the artefact it was ingested from, so a rebuilt step replaces
# its own rows and an unchanged one is read again without recomputation.
stations = Table(
    "stations",
    metadata,
    _artifact_key("stations_key"),
    Column("station_id", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("lat", Double, nullable=False),
    Column("lon", Double, nullable=False),
    PrimaryKeyConstraint("stations_key", "station_id", name="pk_stations"),
    CheckConstraint(one_of("kind", ("pt", "bs")), name="kind"),
)

hubs = Table(
    "hubs",
    metadata,
    _artifact_key("hubs_key"),
    Column("hub_id", Text, nullable=False),
    Column("label", Text, nullable=False),
    Column("lat", Double, nullable=False),
    Column("lon", Double, nullable=False),
    Column("outline", JSONB),
    Column("pt_station_ids", JSONB, nullable=False),
    Column("bike_station_ids", JSONB, nullable=False),
    Column("lines", JSONB, nullable=False),
    PrimaryKeyConstraint("hubs_key", "hub_id", name="pk_hubs"),
)

station_hubs = Table(
    "station_hubs",
    metadata,
    _artifact_key("hubs_key"),
    Column("station_id", Text, nullable=False),
    Column("hub_id", Text, nullable=False),
    PrimaryKeyConstraint("hubs_key", "station_id", name="pk_station_hubs"),
)

hub_pairs = Table(
    "hub_pairs",
    metadata,
    _artifact_key("instance_key"),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("demand", Double, nullable=False),
    Column("euclid_dist_m", Double, nullable=False),
    PrimaryKeyConstraint("instance_key", "origin_hub", "destination_hub", name="pk_hub_pairs"),
)

# The pairs the routes step routed, keyed by the routes artefact: the map draws them while step 4
# has not stored `hub_pairs` yet.
route_pairs = Table(
    "route_pairs",
    metadata,
    _artifact_key("instance_key"),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    PrimaryKeyConstraint("instance_key", "origin_hub", "destination_hub", name="pk_route_pairs"),
)

# The six parser columns stay null until the package's parser fills them (story 2-7).
route_options = Table(
    "route_options",
    metadata,
    _artifact_key("instance_key"),
    Column("arc_id", Text, nullable=False),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("total_travel_time_s", Double, nullable=False),
    Column("total_transfer_time_s", Double, nullable=False),
    Column("total_distance_m", Double, nullable=False),
    Column("legs", JSONB, nullable=False),
    Column("geometry", JSONB, nullable=False),
    Column("bike_legs", Integer),
    Column("bike_time_min", Double),
    Column("pt_time_min", Double),
    Column("transfer_time_min", Double),
    Column("parking_time_min", Double),
    Column("car_cost_chf", Double),
    PrimaryKeyConstraint("instance_key", "arc_id", name="pk_route_options"),
    CheckConstraint(one_of("mode", ROUTE_MODES), name="mode"),
)

station_bikes = Table(
    "station_bikes",
    metadata,
    _artifact_key("instance_key"),
    Column("station_id", Text, nullable=False),
    Column("capacity", Double, nullable=False),
    Column("inventory_start", Double, nullable=False),
    PrimaryKeyConstraint("instance_key", "station_id", name="pk_station_bikes"),
)

option_station_deltas = Table(
    "option_station_deltas",
    metadata,
    _artifact_key("instance_key"),
    Column("arc_id", Text, nullable=False),
    Column("station_id", Text, nullable=False),
    Column("delta", Double, nullable=False),
    PrimaryKeyConstraint("instance_key", "arc_id", "station_id", name="pk_option_station_deltas"),
)

# One row per failed trip-planner query, written as the routes step reports it.
route_failures = Table(
    "route_failures",
    metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("run_id", Text, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
    Column(
        "run_step_id", BigInteger, ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=False
    ),
    Column("instance_period_id", Text, ForeignKey("instance_periods.id", ondelete="CASCADE")),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("query", Text, nullable=False),
    Column("kind", Text, nullable=False),
    Column("message", Text, nullable=False),
    Column("attempts", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(one_of("query", ("pt_bike", "car")), name="query"),
    CheckConstraint(one_of("kind", ("technical", "no_route")), name="kind"),
    CheckConstraint("attempts >= 1", name="attempts"),
    Index("ix_route_failures_run_id", "run_id"),
)


# The result of the pricing model for one pricing version and period. Two versions with the same
# solver inputs point to one artefact (`input_key`); each has its own row, which carries the
# quality and the provenance of the solve it reuses.
solves = Table(
    "solves",
    metadata,
    Column("id", Text, primary_key=True),
    Column("pricing_version_id", Text, ForeignKey("pricing_versions.id"), nullable=False),
    Column("period_id", Text, ForeignKey("instance_periods.id"), nullable=False),
    Column("input_key", Text, ForeignKey("artifacts.input_key"), nullable=False),
    Column("solver_status", Integer, nullable=False),
    Column("solver_status_name", Text, nullable=False),
    Column("objective_value", Double),
    Column("gap_pct", Double),
    Column("solution_time_s", Double),
    Column("sol_count", Integer, nullable=False),
    Column("time_limit_reached", Boolean, nullable=False),
    Column("gurobi_version", Text, nullable=False),
    Column("licence_kind", Text, nullable=False),
    Column("solver_parameters", JSONB, nullable=False),
    Column("package_fingerprint", Text, nullable=False),
    Column("demonstrator_version", Text, nullable=False),
    Column("dependency_lock_sha256", Text, nullable=False),
    Column("platform", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("pricing_version_id", "period_id", name="uq_solves_pricing_version_id"),
)


def _solve_key(name: str = "solve_key") -> Column[str]:
    return Column(name, Text, ForeignKey("artifacts.input_key", ondelete="CASCADE"), nullable=False)


solve_rows = Table(
    "solve_rows",
    metadata,
    _solve_key(),
    Column("arc_id", Text, nullable=False),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("type", Text, nullable=False),
    Column("nu", Double, nullable=False),
    Column("flow", Double, nullable=False),
    Column("bike_price", Double),
    Column("total_price", Double),
    Column("z_value", Double),
    Column("relaxation_difference", Double),
    PrimaryKeyConstraint("solve_key", "arc_id", name="pk_solve_rows"),
    CheckConstraint(one_of("type", SOLVE_ROW_TYPES), name="type"),
)

solve_ods = Table(
    "solve_ods",
    metadata,
    _solve_key(),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("gamma", Double, nullable=False),
    PrimaryKeyConstraint("solve_key", "origin_hub", "destination_hub", name="pk_solve_ods"),
)

# A simulation is content-keyed: its key hashes what it read, so a row is never overwritten and
# no foreign key points at the keys it names. The links say which pricing version uses it.
simulations = Table(
    "simulations",
    metadata,
    Column("simulation_key", Text, primary_key=True),
    Column("instance_key", Text, nullable=False),
    Column("period_id", Text, nullable=False),
    Column("rule_id", Text, nullable=False),
    Column("rule_version", Integer, nullable=False),
    Column("rule_parameters", JSONB, nullable=False),
    Column("price_scheme", Text, nullable=False),
    Column("solve_key", Text),
    Column("flat_price_kind", Text),
    Column("flat_price_amount_chf", Double),
    Column("pt_fare_chf", Double, nullable=False),
    Column("car_parking_fee_chf", Double, nullable=False),
    Column("travellers", Integer, nullable=False),
    Column("displaced", Integer, nullable=False),
    Column("unserved", Integer, nullable=False),
    Column("bike_rides", Integer, nullable=False),
    Column("bike_revenue_chf", Double, nullable=False),
    Column("stations_empty", Integer, nullable=False),
    Column("stations_full", Integer, nullable=False),
    Column("adapter", Text, nullable=False),
    Column("package_fingerprint", Text),
    Column("demonstrator_version", Text, nullable=False),
    Column("duration_s", Double, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(one_of("price_scheme", PRICE_SCHEMES), name="price_scheme"),
    CheckConstraint(one_of("adapter", SIMULATION_ADAPTERS), name="adapter"),
)


def _simulation_key() -> Column[str]:
    return Column(
        "simulation_key",
        Text,
        ForeignKey("simulations.simulation_key", ondelete="CASCADE"),
        nullable=False,
    )


simulation_modes = Table(
    "simulation_modes",
    metadata,
    _simulation_key(),
    Column("mode", Text, nullable=False),
    Column("travellers", Integer, nullable=False),
    PrimaryKeyConstraint("simulation_key", "mode", name="pk_simulation_modes"),
    CheckConstraint(one_of("mode", ROUTE_MODES), name="mode"),
)

simulation_choices = Table(
    "simulation_choices",
    metadata,
    _simulation_key(),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("arc_id", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("travellers", Integer, nullable=False),
    Column("price_chf", Double, nullable=False),
    Column("displaced", Integer, nullable=False),
    PrimaryKeyConstraint(
        "simulation_key", "origin_hub", "destination_hub", "arc_id", name="pk_simulation_choices"
    ),
    CheckConstraint(one_of("mode", ROUTE_MODES), name="mode"),
)

simulation_pairs = Table(
    "simulation_pairs",
    metadata,
    _simulation_key(),
    Column("origin_hub", Text, nullable=False),
    Column("destination_hub", Text, nullable=False),
    Column("unserved", Integer, nullable=False),
    PrimaryKeyConstraint(
        "simulation_key", "origin_hub", "destination_hub", name="pk_simulation_pairs"
    ),
)

simulation_stations = Table(
    "simulation_stations",
    metadata,
    _simulation_key(),
    Column("station_id", Text, nullable=False),
    Column("bikes_end", Double, nullable=False),
    Column("empty", Boolean, nullable=False),
    Column("full", Boolean, nullable=False),
    PrimaryKeyConstraint("simulation_key", "station_id", name="pk_simulation_stations"),
)

pricing_version_simulations = Table(
    "pricing_version_simulations",
    metadata,
    # Named by hand: the generated name would exceed PostgreSQL's 63 characters.
    Column(
        "pricing_version_id",
        Text,
        ForeignKey("pricing_versions.id", name="fk_pvs_pricing_version_id_pricing_versions"),
        nullable=False,
    ),
    Column("period_id", Text, ForeignKey("instance_periods.id"), nullable=False),
    Column("price_scheme", Text, nullable=False),
    Column("rule_id", Text, nullable=False),
    Column("rule_version", Integer, nullable=False),
    Column("simulation_key", Text, ForeignKey("simulations.simulation_key"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "pricing_version_id",
        "period_id",
        "price_scheme",
        "rule_id",
        "rule_version",
        name="pk_pricing_version_simulations",
    ),
    CheckConstraint(one_of("price_scheme", PRICE_SCHEMES), name="price_scheme"),
)

# The numbers of a solve's result, computed once per derivation version (ARCHITECTURE.md § 5.2).
result_summaries = Table(
    "result_summaries",
    metadata,
    _solve_key(),
    Column("derivation_version", Integer, nullable=False),
    Column("numbers", JSONB, nullable=False),
    Column("package_summary", JSONB),
    Column("objective_residual", Double),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("solve_key", "derivation_version", name="pk_result_summaries"),
)

# The one pricing version (and period) the Home screen shows; deleting the version removes it.
showcase = Table(
    "showcase",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=False),
    Column(
        "pricing_version_id",
        Text,
        ForeignKey("pricing_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("period_id", Text, ForeignKey("instance_periods.id"), nullable=False),
    Column("marked_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("id = 1", name="one_row"),
)
