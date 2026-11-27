import os
import socket
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from pricing_demo.application.errors import (
    NoCityDataYet,
    OtherTimetableInGraphFolder,
    SolveNotFound,
    SolveNotVerifiable,
    VersionNotBuilt,
)
from pricing_demo.application.use_cases.run_build_step import BuildStepExecutor
from pricing_demo.application.use_cases.run_pricing_step import PricingModelStepExecutor
from pricing_demo.application.use_cases.run_simulation_step import TravellerSimulationStepExecutor
from pricing_demo.application.use_cases.show_basemap_bounds import (
    BasemapBounds,
    ShowBasemapBounds,
)
from pricing_demo.application.use_cases.verify_build import VerifyResult
from pricing_demo.application.use_cases.verify_solve import VerifySolveResult
from pricing_demo.domain.build_plan import BUILD_STEPS
from pricing_demo.domain.build_verification import FileComparison
from pricing_demo.domain.city_instances import InstanceVersionNotFound
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.solve_verification import SolveVerification, compare_solve_rows
from pricing_demo.domain.solves import SolveRow
from pricing_demo.domain.system_status import PROBED_COMPONENTS
from pricing_demo.domain.traveller_simulation import SimulationRule
from pricing_demo.infrastructure.config.settings import (
    DEFAULT_GTFS,
    DEFAULT_OSM_DIR,
    DEFAULT_SHAPE_TOOL_IMAGE,
    Settings,
)
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.bus_shape_matcher import FakeBusShapeMatcher
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.graph_fingerprints import FakeGraphFingerprints
from pricing_demo.infrastructure.fakes.hold import HoldingStepExecutor
from pricing_demo.infrastructure.fakes.pricing_solver import FakePricingSolver
from pricing_demo.infrastructure.fakes.simulation_rule import FakeSimulationRule
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.persistence.fake_settings import PostgresFakeSettings
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed
from pricing_demo.infrastructure.pricing_model.city_preparation import PackageCityPreparation
from pricing_demo.infrastructure.pricing_model.pricing_solver import PackagePricingSolver
from pricing_demo.infrastructure.shape_matching.pfaedle import DockerPfaedleMatcher
from pricing_demo.infrastructure.trip_planner.graph_builder import ComposeGraphBuilder
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints
from pricing_demo.infrastructure.worker_build_sources import WorkerBuildSources
from pricing_demo.worker import main as worker_main
from pricing_demo.worker.main import (
    build_probes,
    build_worker,
    simulation_rule_source,
    worker_id_for,
)
from tests.support.runs import T0


def settings_for(tmp_path: Path, **fields: object) -> Settings:
    return Settings(data_dir=tmp_path / "data", **fields)  # type: ignore[arg-type]


def test_the_worker_id_is_host_and_pid_when_none_is_set(tmp_path: Path) -> None:
    assert worker_id_for(settings_for(tmp_path), "laptop", 4242) == "laptop-4242"


def test_the_worker_id_is_the_configured_one_when_set(tmp_path: Path) -> None:
    assert worker_id_for(settings_for(tmp_path, worker_id="w-1"), "laptop", 4242) == "w-1"


def test_building_the_worker_creates_the_data_directory(tmp_path: Path) -> None:
    settings = settings_for(tmp_path)
    assert not settings.data_dir.exists()

    built = build_worker(settings)
    built.engine.dispose()

    assert (settings.data_dir).is_dir()


def test_the_built_worker_identifies_itself_with_the_host_and_the_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PRICING_DEMO_WORKER_ID", raising=False)

    built = build_worker(settings_for(tmp_path))
    built.engine.dispose()

    assert built.identity.host == socket.gethostname()
    assert built.identity.pid == os.getpid()
    assert built.identity.id == f"{socket.gethostname()}-{os.getpid()}"


def test_a_configured_worker_id_is_the_built_workers_id(tmp_path: Path) -> None:
    built = build_worker(settings_for(tmp_path, worker_id="w-9"))
    built.engine.dispose()

    assert built.identity.id == "w-9"


@pytest.mark.parametrize("adapters", ["real", "fake"])
def test_each_adapter_set_builds_a_worker_that_reports_the_probed_components(
    tmp_path: Path, adapters: str
) -> None:
    built = build_worker(settings_for(tmp_path, adapters=adapters))
    built.engine.dispose()

    assert built.worker is not None


def test_the_probes_of_each_adapter_set_cover_the_probed_components(tmp_path: Path) -> None:
    for adapters in ("real", "fake"):
        settings = settings_for(tmp_path, adapters=adapters)
        built = build_worker(settings)
        probes = build_probes(settings, built.engine)
        built.engine.dispose()

        assert sorted(probe.component for probe in probes) == sorted(PROBED_COMPONENTS)


def test_the_report_interval_is_read_from_the_settings(tmp_path: Path) -> None:
    built = build_worker(settings_for(tmp_path, component_report_interval_s=1))
    built.engine.dispose()

    assert built.worker._report_every == timedelta(seconds=1)


# -- city data commands ------------------------------------------------------------------


def test_no_subcommand_runs_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []
    monkeypatch.setattr(worker_main, "run_loop", lambda: ran.append("loop"))

    assert worker_main.main([]) is None
    assert ran == ["loop"]


def test_import_city_data_defaults_to_the_repository_timetable_and_the_otp_folder() -> None:
    args = worker_main.parser().parse_args(["import-city-data"])

    assert args.command == "import-city-data"
    assert args.gtfs == DEFAULT_GTFS
    assert args.osm_dir == DEFAULT_OSM_DIR
    assert DEFAULT_GTFS.name == "tpg_gtfs.zip"
    assert DEFAULT_GTFS.parent.name == "OTP2_Geneva_Instances"
    assert DEFAULT_OSM_DIR.parts[-2:] == ("otp", "data")


def test_import_city_data_takes_its_inputs_from_the_command_line(tmp_path: Path) -> None:
    args = worker_main.parser().parse_args(
        ["import-city-data", "--gtfs", str(tmp_path / "x.zip"), "--osm-dir", str(tmp_path)]
    )

    assert (args.gtfs, args.osm_dir) == (tmp_path / "x.zip", tmp_path)


@pytest.mark.parametrize(
    ("adapters", "feed"), [("fake", FixtureBikeStationFeed), ("real", PackageBikeStationFeed)]
)
def test_the_feed_is_chosen_by_the_adapter_set(tmp_path: Path, adapters: str, feed: type) -> None:
    assert isinstance(
        worker_main.build_bike_station_feed(settings_for(tmp_path, adapters=adapters)), feed
    )


def test_the_fake_adapter_set_draws_the_bus_legs_without_docker(tmp_path: Path) -> None:
    matcher = worker_main.build_bus_shape_matcher(settings_for(tmp_path, adapters="fake"))

    assert isinstance(matcher, FakeBusShapeMatcher)


def test_the_real_adapter_set_runs_the_configured_image_in_docker(tmp_path: Path) -> None:
    matcher = worker_main.build_bus_shape_matcher(
        settings_for(tmp_path, adapters="real", shape_tool_image="example/pfaedle:1")
    )

    assert isinstance(matcher, DockerPfaedleMatcher)
    assert matcher.image == "example/pfaedle:1"


def test_the_real_matcher_defaults_to_the_pinned_pfaedle_image(tmp_path: Path) -> None:
    matcher = worker_main.build_bus_shape_matcher(settings_for(tmp_path, adapters="real"))

    assert matcher.image == DEFAULT_SHAPE_TOOL_IMAGE
    assert "@sha256:" in matcher.image


def test_each_subcommand_builds_its_use_case_and_prints_the_new_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, tuple[object, ...]]] = []

    class Created:
        id = "geneva-2026-11-26"

    class FakeImport:
        def execute(self, gtfs: Path, osm_dir: Path) -> Created:
            calls.append(("import", (gtfs, osm_dir)))
            return Created()

    class FakeRefresh:
        def execute(self) -> Created:
            calls.append(("refresh", ()))
            return Created()

    monkeypatch.setattr(
        worker_main, "build_import_city_data", lambda settings, engine: FakeImport()
    )
    monkeypatch.setattr(
        worker_main, "build_refresh_bike_stations", lambda settings, engine: FakeRefresh()
    )
    settings = settings_for(tmp_path)

    first = worker_main.run_command(
        worker_main.parser().parse_args(["import-city-data", "--gtfs", "g.zip", "--osm-dir", "o"]),
        settings,
    )
    second = worker_main.run_command(
        worker_main.parser().parse_args(["refresh-bike-stations"]), settings
    )

    assert (first, second) == (0, 0)
    assert calls == [("import", (Path("g.zip"), Path("o"))), ("refresh", ())]
    assert capsys.readouterr().out == "geneva-2026-11-26\ngeneva-2026-11-26\n"


def test_an_application_error_goes_to_stderr_with_exit_code_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Refusing:
        def execute(self) -> None:
            raise NoCityDataYet

    monkeypatch.setattr(
        worker_main, "build_refresh_bike_stations", lambda settings, engine: Refusing()
    )

    code = worker_main.run_command(
        worker_main.parser().parse_args(["refresh-bike-stations"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert "No city data is imported yet" in captured.err


def test_main_returns_the_exit_code_of_a_subcommand(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_main, "run_command", lambda args, settings: 1)

    assert worker_main.main(["refresh-bike-stations"]) == 1


# -- the graph command and the graph fingerprint ------------------------------------------


def test_otp_graph_parses_with_and_without_a_data_set() -> None:
    assert worker_main.parser().parse_args(["otp-graph"]).dataset is None
    args = worker_main.parser().parse_args(["otp-graph", "--dataset", "geneva-2026-11-26"])

    assert (args.command, args.dataset) == ("otp-graph", "geneva-2026-11-26")


def test_otp_graph_prints_the_manifest_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[str | None] = []

    class FakeBuild:
        def execute(self, dataset_id: str | None) -> Path:
            asked.append(dataset_id)
            return tmp_path / "graph-manifest.json"

    monkeypatch.setattr(worker_main, "build_build_trip_planner_graph", lambda s, e: FakeBuild())

    code = worker_main.run_command(
        worker_main.parser().parse_args(["otp-graph", "--dataset", "d1"]), settings_for(tmp_path)
    )

    assert (code, asked) == (0, ["d1"])
    assert capsys.readouterr().out == f"{tmp_path / 'graph-manifest.json'}\n"


def test_otp_graph_exits_one_with_the_reason_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Refusing:
        def execute(self, dataset_id: str | None) -> Path:
            raise OtherTimetableInGraphFolder(["tpg_gtfs.zip"])

    monkeypatch.setattr(worker_main, "build_build_trip_planner_graph", lambda s, e: Refusing())

    code = worker_main.run_command(
        worker_main.parser().parse_args(["otp-graph"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert (code, captured.out) == (1, "")
    assert "tpg_gtfs.zip" in captured.err


@pytest.mark.parametrize("adapters", ["fake", "real"])
def test_the_graph_is_built_by_compose_in_both_adapter_sets(tmp_path: Path, adapters: str) -> None:
    settings = settings_for(tmp_path, adapters=adapters, otp_graph_dir=tmp_path / "graph")
    engine = create_db_engine(settings.database_url)
    try:
        use_case = worker_main.build_build_trip_planner_graph(settings, engine)
    finally:
        engine.dispose()

    assert isinstance(use_case._builder, ComposeGraphBuilder)
    assert use_case._folder._path == tmp_path / "graph"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("adapters", "preparation"), [("fake", FakeCityPreparation), ("real", PackageCityPreparation)]
)
def test_each_adapter_set_registers_the_build_steps_with_its_own_preparation(
    tmp_path: Path, adapters: str, preparation: type
) -> None:
    built = build_worker(settings_for(tmp_path, adapters=adapters))
    built.engine.dispose()

    registry = built.worker._process._registry
    for step in BUILD_STEPS:
        executor = registry.executor_for(step)
        assert isinstance(executor, BuildStepExecutor)
        assert isinstance(executor._preparation, preparation)
        assert registry.keeper_for(step) is not None


def test_the_fake_set_registers_both_pricing_steps(tmp_path: Path) -> None:
    built = build_worker(settings_for(tmp_path, adapters="fake"))
    built.engine.dispose()

    registry = built.worker._process._registry
    model = registry.executor_for(StepName.PRICING_MODEL)
    simulation = registry.executor_for(StepName.TRAVELLER_SIMULATION)
    assert isinstance(model, PricingModelStepExecutor)
    assert isinstance(model._solver, FakePricingSolver)
    assert registry.keeper_for(StepName.PRICING_MODEL) is model
    # The fake set wraps the simulation in the test hold of step 5b; the keeper stays the inner one.
    assert isinstance(simulation, HoldingStepExecutor)
    keeper = registry.keeper_for(StepName.TRAVELLER_SIMULATION)
    assert isinstance(keeper, TravellerSimulationStepExecutor)
    assert simulation._inner is keeper
    # The rule is read from the fake settings at each call; the callable is not called here
    # because the settings are a database row.
    assert isinstance(keeper._rule.__self__, FakeSimulationRule)  # type: ignore[attr-defined]


def test_the_real_set_registers_the_package_solver_and_the_simulation_step(
    tmp_path: Path,
) -> None:
    built = build_worker(settings_for(tmp_path, adapters="real"))
    built.engine.dispose()

    registry = built.worker._process._registry
    model = registry.executor_for(StepName.PRICING_MODEL)
    assert isinstance(model, PricingModelStepExecutor)
    assert isinstance(model._solver, PackagePricingSolver)
    assert registry.keeper_for(StepName.PRICING_MODEL) is model
    assert isinstance(
        registry.executor_for(StepName.TRAVELLER_SIMULATION), TravellerSimulationStepExecutor
    )


@pytest.mark.parametrize("adapters", ["fake", "real"])
def test_the_worker_records_the_simulation_rule_it_chose(
    tmp_path: Path, adapters: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fake set reads its rule from the settings row: none is staged.
    monkeypatch.setattr(PostgresFakeSettings, "read", lambda self: {})
    built = build_worker(settings_for(tmp_path, adapters=adapters))
    built.engine.dispose()

    assert built.worker._simulation_rule is not None
    assert built.worker._simulation_rule() == {
        "id": "balanced-score",
        "version": 1,
        "parameters": {"price_weight": 0.5, "time_weight": 0.5},
    }


def test_the_fake_worker_reports_and_plans_with_the_same_graph_fingerprints(
    tmp_path: Path,
) -> None:
    built = build_worker(settings_for(tmp_path, adapters="fake"))
    built.engine.dispose()

    reported = built.worker._report._graph
    executor = built.worker._process._registry.executor_for(StepName.AREA)
    assert isinstance(reported, FakeGraphFingerprints)
    assert isinstance(executor, BuildStepExecutor)
    assert isinstance(executor._sources, WorkerBuildSources)
    assert executor._sources._graph is reported


def test_the_worker_reports_the_graph_in_the_graph_folder(tmp_path: Path) -> None:
    for adapters in ("real", "fake"):
        settings = settings_for(tmp_path, adapters=adapters, otp_graph_dir=tmp_path / "g")
        built = build_worker(settings)
        built.engine.dispose()

        fingerprints = built.worker._report._graph
        assert isinstance(fingerprints, FileGraphFingerprints)
        assert fingerprints._path == tmp_path / "g"


# -- the basemap bounds command ------------------------------------------------------------


def test_basemap_bounds_parses_with_and_without_a_data_set() -> None:
    assert worker_main.parser().parse_args(["basemap-bounds"]).dataset is None
    args = worker_main.parser().parse_args(["basemap-bounds", "--dataset", "d1"])

    assert (args.command, args.dataset) == ("basemap-bounds", "d1")


def test_basemap_bounds_prints_the_id_and_the_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    datasets = InMemoryCityDatasets()
    datasets.add(fake_city_dataset("d1", T0))
    asked: list[str | None] = []

    class Showing(ShowBasemapBounds):
        def execute(self, dataset_id: str | None) -> BasemapBounds:
            asked.append(dataset_id)
            return super().execute(dataset_id)

    monkeypatch.setattr(worker_main, "build_show_basemap_bounds", lambda e: Showing(datasets))

    code = worker_main.run_command(
        worker_main.parser().parse_args(["basemap-bounds", "--dataset", "d1"]),
        settings_for(tmp_path),
    )

    area = fake_city_dataset("d1", T0).available_area
    assert (code, asked) == (0, ["d1"])
    assert capsys.readouterr().out == (
        f"d1 {area.min_lon},{area.min_lat},{area.max_lon},{area.max_lat}\n"
    )


def test_basemap_bounds_exits_one_with_the_reason_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        worker_main,
        "build_show_basemap_bounds",
        lambda e: ShowBasemapBounds(InMemoryCityDatasets()),
    )

    code = worker_main.run_command(
        worker_main.parser().parse_args(["basemap-bounds"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert (code, captured.out) == (1, "")
    assert "No city data is imported yet" in captured.err


def test_the_basemap_bounds_use_case_reads_the_database_data_sets(tmp_path: Path) -> None:
    engine = create_db_engine(settings_for(tmp_path).database_url)
    try:
        use_case = worker_main.build_show_basemap_bounds(engine)
    finally:
        engine.dispose()

    assert isinstance(use_case, ShowBasemapBounds)


def verify_result(match: bool) -> object:
    from pricing_demo.domain.build_verification import BuildComparison, StepComparison

    return VerifyResult(
        comparison=BuildComparison(
            tuple(StepComparison(step, ()) for step in BUILD_STEPS)
            if match
            else (StepComparison(StepName.AREA, (FileComparison("a", "1", "2"),)),)
        )
    )


def test_verify_build_parses_its_version() -> None:
    assert worker_main.parser().parse_args(["verify-build", "geneva-3km.v1"]).version == (
        "geneva-3km.v1"
    )


@pytest.mark.parametrize(("match", "code"), [(True, 0), (False, 1)])
def test_verify_build_prints_the_report_and_exits_zero_or_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    match: bool,
    code: int,
) -> None:
    class Verifying:
        def execute(self, version_id: str, stop: object) -> object:
            assert version_id == "geneva-3km.v1"
            return verify_result(match)

    monkeypatch.setattr(worker_main, "build_verify_build", lambda s, e: Verifying())

    exit_code = worker_main.run_command(
        worker_main.parser().parse_args(["verify-build", "geneva-3km.v1"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert exit_code == code
    assert captured.err == ""
    assert captured.out.splitlines()[-1] == (
        f"verify-build geneva-3km.v1: {'match' if match else 'differ'}"
    )


@pytest.mark.parametrize(
    "error",
    [
        VersionNotBuilt("v.v1"),
        InstanceVersionNotFound("v.v1"),
        FileNotFoundError("od_routes.json"),
        ValueError("Instance_1.json does not have the expected shape"),
    ],
)
def test_verify_build_exits_two_with_the_reason_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    class Refusing:
        def execute(self, version_id: str, stop: object) -> object:
            raise error

    monkeypatch.setattr(worker_main, "build_verify_build", lambda s, e: Refusing())

    code = worker_main.run_command(
        worker_main.parser().parse_args(["verify-build", "v.v1"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "v.v1" in captured.err


def test_verify_build_exits_two_naming_the_step_and_code_of_a_failed_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Failing:
        def execute(self, version_id: str, stop: object) -> VerifyResult:
            return VerifyResult(failure=(StepName.ROUTES, "trip_planner_unreachable", "down"))

    monkeypatch.setattr(worker_main, "build_verify_build", lambda s, e: Failing())

    code = worker_main.run_command(
        worker_main.parser().parse_args(["verify-build", "v.v1"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "routes" in captured.err
    assert "trip_planner_unreachable" in captured.err
    assert "down" in captured.err


def test_main_returns_the_code_of_verify_build(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_main, "run_command", lambda args, settings: 2)

    assert worker_main.main(["verify-build", "v.v1"]) == 2


@pytest.mark.parametrize(
    ("adapters", "preparation"), [("fake", FakeCityPreparation), ("real", PackageCityPreparation)]
)
def test_verify_build_rebuilds_with_the_preparation_of_the_adapter_set(
    tmp_path: Path, adapters: str, preparation: type
) -> None:
    engine = create_db_engine(settings_for(tmp_path).database_url)
    try:
        verifying = worker_main.build_verify_build(
            settings_for(tmp_path, adapters=adapters), engine
        )
    finally:
        engine.dispose()

    assert isinstance(verifying._preparation, preparation)


def solve_verification(match: bool) -> VerifySolveResult:
    rows = [SolveRow("1b", "A", "B", "PT+Bike", 1.0, 4.0, 1.5, 3.5, 0.0, 0.0)]
    changed = [replace(rows[0], bike_price=1.6)]
    return VerifySolveResult(
        SolveVerification((compare_solve_rows(rows, rows if match else changed),))
    )


def test_verify_parses_its_solve_id() -> None:
    args = worker_main.parser().parse_args(["verify", "geneva-3km.v1.B.mon-08"])

    assert (args.command, args.solve) == ("verify", "geneva-3km.v1.B.mon-08")


@pytest.mark.parametrize(("match", "code"), [(True, 0), (False, 1)])
def test_verify_prints_the_report_and_exits_zero_or_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    match: bool,
    code: int,
) -> None:
    class Verifying:
        def execute(self, solve_id: str, stop: object) -> VerifySolveResult:
            assert solve_id == "v.v1.B.mon-08"
            return solve_verification(match)

    monkeypatch.setattr(worker_main, "build_verify_solve", lambda s, e: Verifying())

    exit_code = worker_main.run_command(
        worker_main.parser().parse_args(["verify", "v.v1.B.mon-08"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert exit_code == code
    assert captured.err == ""
    assert captured.out.splitlines()[-1] == (
        f"verify v.v1.B.mon-08: {'match' if match else 'differ'}"
    )
    if not match:
        assert captured.out.splitlines()[0] == (
            "solve_rows [A>B 1b] bike_price: stored 1.5, re-run 1.6"
        )


@pytest.mark.parametrize(
    "error",
    [
        SolveNotFound("v.v1.B.mon-08"),
        SolveNotVerifiable("v.v1.B.mon-08", "no simulation is stored for it"),
        FileNotFoundError("Instance_1.json"),
    ],
)
def test_verify_exits_two_with_the_reason_on_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    class Refusing:
        def execute(self, solve_id: str, stop: object) -> VerifySolveResult:
            raise error

    monkeypatch.setattr(worker_main, "build_verify_solve", lambda s, e: Refusing())

    code = worker_main.run_command(
        worker_main.parser().parse_args(["verify", "v.v1.B.mon-08"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err != ""


def test_verify_exits_two_naming_the_code_of_a_failed_re_solve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Failing:
        def execute(self, solve_id: str, stop: object) -> VerifySolveResult:
            return VerifySolveResult(failure=("solver_no_solution", "status INFEASIBLE"))

    monkeypatch.setattr(worker_main, "build_verify_solve", lambda s, e: Failing())

    code = worker_main.run_command(
        worker_main.parser().parse_args(["verify", "v.v1.B.mon-08"]), settings_for(tmp_path)
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "solver_no_solution" in captured.err
    assert "status INFEASIBLE" in captured.err


def test_main_returns_the_code_of_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_main, "run_command", lambda args, settings: 1)

    assert worker_main.main(["verify", "v.v1.B.mon-08"]) == 1


@pytest.mark.parametrize(
    ("adapters", "solver"), [("fake", FakePricingSolver), ("real", PackagePricingSolver)]
)
def test_verify_re_solves_with_the_solver_of_the_adapter_set(
    tmp_path: Path, adapters: str, solver: type
) -> None:
    engine = create_db_engine(settings_for(tmp_path).database_url)
    try:
        verifying = worker_main.build_verify_solve(
            settings_for(tmp_path, adapters=adapters), engine
        )
    finally:
        engine.dispose()

    assert isinstance(verifying._solver, solver)


def test_the_fake_set_reads_the_staged_rule_and_the_real_set_keeps_its_own() -> None:
    settings = InMemoryFakeSettings()
    source = simulation_rule_source(settings)

    assert SimulationRule.of(source()).version == 1

    settings.set_pricing_model(
        {"simulation_rule": {"version": 2, "price_weight": 0.6, "time_weight": 0.4}}
    )

    assert SimulationRule.of(source()) == SimulationRule(
        "balanced-score", 2, {"price_weight": 0.6, "time_weight": 0.4}
    )
    assert SimulationRule.of(simulation_rule_source(None)()).version == 1


def test_the_fake_worker_simulates_and_records_with_the_same_rule_source(tmp_path: Path) -> None:
    built = build_worker(settings_for(tmp_path, adapters="fake"))
    built.engine.dispose()

    registry = built.worker._process._registry
    simulation = registry.executor_for(StepName.TRAVELLER_SIMULATION)
    assert isinstance(simulation, HoldingStepExecutor)
    keeper = registry.keeper_for(StepName.TRAVELLER_SIMULATION)
    assert isinstance(keeper, TravellerSimulationStepExecutor)
    assert simulation._inner is keeper
    assert isinstance(keeper._rule.__self__, FakeSimulationRule)  # type: ignore[attr-defined]
