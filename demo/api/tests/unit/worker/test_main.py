import os
import socket
from datetime import timedelta
from pathlib import Path

import pytest

from pricing_demo.application.errors import NoCityDataYet
from pricing_demo.domain.system_status import PROBED_COMPONENTS
from pricing_demo.infrastructure.config.settings import DEFAULT_GTFS, DEFAULT_OSM_DIR, Settings
from pricing_demo.infrastructure.fakes.bike_station_feed import FixtureBikeStationFeed
from pricing_demo.infrastructure.pricing_model.bike_station_feed import PackageBikeStationFeed
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
