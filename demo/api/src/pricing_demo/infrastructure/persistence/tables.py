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
VERSION_STATUSES = ("draft", "sealed")
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
)

runs = Table(
    "runs",
    metadata,
    Column("id", Text, primary_key=True),
    Column("kind", Text, nullable=False),
    Column("instance_version_id", Text, ForeignKey("instance_versions.id")),
    Column("pricing_version_id", Text),
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
# defaults of `PipelineConfig`, `InstanceParams` and `OptimizerParams`.
package_fingerprints = Table(
    "package_fingerprints",
    metadata,
    Column("fingerprint", Text, primary_key=True),
    Column("version", Text, nullable=False),
    Column("git_commit", Text, nullable=False),
    Column("git_dirty", Boolean, nullable=False),
    Column("defaults", JSONB, nullable=False),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
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
    CheckConstraint(one_of("step", BUILD_STEP_NAMES), name="step"),
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
    CheckConstraint(one_of("mode", ("pt_bike", "pt_only", "car")), name="mode"),
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
