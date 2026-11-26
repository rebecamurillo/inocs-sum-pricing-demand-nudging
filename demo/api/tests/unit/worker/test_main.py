import os
import socket
from datetime import timedelta
from pathlib import Path

import pytest

from pricing_demo.application.errors import NoCityDataYet, OtherTimetableInGraphFolder
from pricing_demo.domain.system_status import PROBED_COMPONENTS
from pricing_demo.infrastructure.config.settings import (
    DEFAULT_GTFS,
    DEFAULT_OSM_DIR,
    DEFAULT_SHAPE_TOOL_IMAGE,
    Settings,
)
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.fakes.bus_shape_matcher import FakeBusShapeMatcher
from pricing_demo.infrastructure.persistence.engine import create_db_engine
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed
from pricing_demo.infrastructure.shape_matching.pfaedle import DockerPfaedleMatcher
from pricing_demo.infrastructure.trip_planner.graph_builder import ComposeGraphBuilder
from pricing_demo.infrastructure.trip_planner.graph_fingerprints import FileGraphFingerprints
from pricing_demo.worker import main as worker_main
from pricing_demo.worker.main import build_probes, build_worker, worker_id_for


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


def test_the_worker_reports_the_graph_in_the_graph_folder(tmp_path: Path) -> None:
    for adapters in ("real", "fake"):
        settings = settings_for(tmp_path, adapters=adapters, otp_graph_dir=tmp_path / "g")
        built = build_worker(settings)
        built.engine.dispose()

        fingerprints = built.worker._report._graph
        assert isinstance(fingerprints, FileGraphFingerprints)
        assert fingerprints._path == tmp_path / "g"
