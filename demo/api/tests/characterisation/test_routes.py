"""Step 3 of a build, run by the real adapter and its child process against a local
OpenTripPlanner stub (`otp_stub.py`): the templates, the retries, the dropped pairs and options,
the sorted file and the failures. Needs no licence, trip planner or internet."""

import itertools
import json
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.pricing_model import routes_progress as templates
from pricing_demo.infrastructure.pricing_model.routes_file import sorted_routes
from tests.characterisation.otp_stub import CAR, PT, OtpStub
from tests.characterisation.rig import FIXTURES, City, make_city

pytestmark = pytest.mark.characterisation

NEVER = threading.Event()
RETRIES = 2
WAIT_S = 0.2
PROBE = Path(__file__).parent / "routes_probe.py"
PACKAGE = (
    Path(__file__).resolve().parents[4] / "sum_nsm_dynamic_pricing/src/sum_nsm_dynamic_pricing"
)


def read(folder: Path, name: str) -> Any:
    return json.loads((folder / name).read_text(encoding="utf-8"))


def city_on(tmp_path: Path, url: str) -> City:
    return make_city(
        tmp_path / "data",
        None,
        FIXTURES / "gbfs_station_information.json",
        otp_url=url,
        retries=RETRIES,
        retry_wait_s=WAIT_S,
    )


def hubs_folder(city: City, folder: Path) -> None:
    for step in (StepName.AREA, StepName.HUBS):
        assert city.prepare(folder, step, NEVER).failure_code is None


def routes(
    city: City, folder: Path
) -> tuple[StepOutcome, list[RouteFailure], list[tuple[int, int]]]:
    hubs_folder(city, folder)
    failures: list[RouteFailure] = []
    steps: list[tuple[int, int]] = []
    outcome = city.port.prepare(
        city.request(folder, StepName.ROUTES),
        lambda done, total: steps.append((done, total)),
        NEVER,
        failures.append,
    )
    return outcome, failures, steps


def templates_logged(folder: Path) -> set[str]:
    lines = (folder / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    return {json.loads(line)["template"] for line in lines}


def probe(folder: Path, url: str) -> list[dict[str, Any]]:
    """`build_od_routes` alone in a fresh interpreter: no quality check, no sort."""
    done = subprocess.run(
        [sys.executable, str(PROBE), str(folder), url, str(RETRIES), str(WAIT_S)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)  # type: ignore[no-any-return]


def test_the_templates_are_the_texts_the_package_logs() -> None:
    source = (PACKAGE / "routing/route_builder.py").read_text(encoding="utf-8")
    source += (PACKAGE / "quality.py").read_text(encoding="utf-8")
    for template in (
        templates.PT_FAILED,
        templates.PT_NONE,
        templates.PT_UNCLASSIFIED,
        templates.CAR_DONE,
        templates.CAR_FAILED,
        templates.CLEANUP_REMOVED,
    ):
        assert f'"{template}"' in source, template
    assert "Route building: %d total OD pairs | %d already cached | %d to query " in source
    assert "(workers=%d, delay=%.2fs)" in source


def test_a_run_logs_the_total_each_pair_and_the_cleanup_with_the_adapters_templates(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    otp_stub.fail("1|0", CAR, 503)
    folder = tmp_path / "w"

    outcome, failures, steps = routes(city_on(tmp_path, otp_stub.url), folder)

    assert outcome.failure_code is None, outcome.failure_reason
    logged = templates_logged(folder)
    assert {
        templates.ROUTE_TOTAL,
        templates.CAR_DONE,
        templates.CAR_FAILED,
        templates.CLEANUP_REMOVED,
    } <= logged
    assert dict(outcome.counts) == {
        "hub_pairs_requested": 2,
        "hub_pairs_removed": 1,
        "retries": RETRIES,
    }
    assert [(f.origin_hub, f.destination_hub, f.query, f.kind, f.attempts) for f in failures] == [
        ("1", "0", "car", "technical", 1 + RETRIES)
    ]
    # Progress is read every 0.5 s and only changes are reported, so whether (0, 2) is seen
    # depends on the host's speed: every report has the total, done never goes down, and the
    # last report is the end.
    assert steps
    assert all(total == 2 for _, total in steps)
    assert [done for done, _ in steps] == sorted(done for done, _ in steps)
    assert steps[-1] == (2, 2)


def test_a_pair_the_trip_planner_cannot_answer_for_public_transport_is_dropped(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    otp_stub.fail("1|0", PT, 503)
    folder = tmp_path / "w"

    outcome, failures, _ = routes(city_on(tmp_path, otp_stub.url), folder)

    assert outcome.failure_code is None, outcome.failure_reason
    assert templates.PT_FAILED in templates_logged(folder)
    assert [
        (item["from_id"], item["to_id"]) for item in read(folder, "od_routes.json")["od_results"]
    ] == [(0, 1)]
    assert [(f.query, f.kind, f.attempts) for f in failures] == [("pt_bike", "technical", 3)]
    attempts = otp_stub.attempts("1|0", PT)
    assert len(attempts) == 1 + RETRIES
    gaps = [later.at - earlier.at for earlier, later in itertools.pairwise(attempts)]
    assert all(gap >= WAIT_S for gap in gaps)
    assert [item.status for item in attempts] == [503] * (1 + RETRIES)


def test_a_pair_with_no_public_transport_pattern_is_dropped_and_reported_as_no_route(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    otp_stub.empty("1|0", PT)
    folder = tmp_path / "w"

    _, failures, _ = routes(city_on(tmp_path, otp_stub.url), folder)

    assert templates.PT_NONE in templates_logged(folder)
    assert [(f.query, f.kind, f.attempts) for f in failures] == [("pt_bike", "no_route", 1)]


def test_a_pair_without_a_car_option_is_reported_and_removed_by_the_quality_check(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    otp_stub.empty("0|1", CAR)
    folder = tmp_path / "w"

    outcome, failures, _ = routes(city_on(tmp_path, otp_stub.url), folder)

    assert [(f.query, f.kind, f.attempts) for f in failures] == [("car", "no_route", 1)]
    assert outcome.counts["hub_pairs_removed"] == 1
    assert [item["from_id"] for item in read(folder, "od_routes.json")["od_results"]] == [1]


def test_a_bike_only_itinerary_is_not_kept(tmp_path: Path, otp_stub: OtpStub) -> None:
    folder = tmp_path / "w"

    routes(city_on(tmp_path, otp_stub.url), folder)

    pairs = read(folder, "od_routes.json")["od_results"]
    assert len(pairs) == 2
    assert all("arc_bike_only" not in pair for pair in pairs)
    for pair in pairs:
        for arc in pair["arc_pt_bike"] + pair["arc_pt_only"]:
            assert {leg["mode"] for leg in arc["legs"]} != {"BICYCLE"}
        assert len(pair["arc_pt_bike"]) == len(pair["arc_pt_only"]) == 1


def test_a_failing_car_query_keeps_the_pair_with_no_car_option_before_the_quality_check(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    city = city_on(tmp_path, otp_stub.url)
    folder = tmp_path / "w"
    hubs_folder(city, folder)
    otp_stub.fail("0|1", CAR, 503)

    results = probe(folder, otp_stub.url)

    kept = {(item["from_id"], item["to_id"]): item for item in results}
    assert kept[(0, 1)]["arc_car"] == []
    assert kept[(1, 0)]["arc_car"]
    assert len(otp_stub.attempts("0|1", CAR)) == 1 + RETRIES


def test_a_resumed_build_repeats_the_option_ids_of_the_cached_pairs(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    city = city_on(tmp_path, otp_stub.url)
    folder = tmp_path / "w"
    hubs_folder(city, folder)
    otp_stub.fail("1|0", PT, 503)
    first = probe(folder, otp_stub.url)
    assert (folder / "od_cache.json").is_file()
    assert [item["from_id"] for item in first] == [0]
    otp_stub.fail("1|0", PT, 503, times=0)

    second = probe(folder, otp_stub.url)

    ids = [
        arc["arc_id"]
        for item in second
        for key in ("arc_pt_bike", "arc_pt_only", "arc_car")
        for arc in item[key]
    ]
    assert len(second) == 2
    assert len(ids) != len(set(ids))


def test_the_step_starts_with_no_cache_and_leaves_none(tmp_path: Path, otp_stub: OtpStub) -> None:
    city = city_on(tmp_path, otp_stub.url)
    folder = tmp_path / "w"
    hubs_folder(city, folder)
    (folder / "od_cache.json").write_text(json.dumps({"1|0": {"from_id": 1}}), encoding="utf-8")

    outcome = city.prepare(folder, StepName.ROUTES, NEVER)

    assert outcome.failure_code is None, outcome.failure_reason
    assert not (folder / "od_cache.json").exists()
    assert len(read(folder, "od_routes.json")["od_results"]) == 2
    assert len(otp_stub.attempts("1|0", PT)) == 1


def test_the_pairs_are_stored_sorted_by_origin_and_destination(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    folder = tmp_path / "w"

    routes(city_on(tmp_path, otp_stub.url), folder)

    pairs = [
        (item["from_id"], item["to_id"]) for item in read(folder, "od_routes.json")["od_results"]
    ]
    assert pairs == sorted(pairs)


def test_no_pair_with_public_transport_fails_the_step_no_public_transport(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    otp_stub.empty("0|1", PT)
    otp_stub.empty("1|0", PT)
    city = city_on(tmp_path, otp_stub.url)

    outcome, _, _ = routes(city, tmp_path / "w")

    assert outcome.failure_code == "no_public_transport"
    assert outcome.failure_reason == (
        "the trip planner found no public transport route; "
        f"the routing date {city.period.routing_date.isoformat()} may be outside its timetable"
    )
    assert not (tmp_path / "w" / "od_cache.json").exists()


def test_a_trip_planner_that_is_not_there_fails_the_step_trip_planner_unreachable(
    tmp_path: Path,
) -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{closed.getsockname()[1]}/otp/gtfs/v1"
    started = time.monotonic()

    outcome, _, _ = routes(city_on(tmp_path, url), tmp_path / "w")

    assert outcome.failure_code == "trip_planner_unreachable"
    assert outcome.failure_reason == f"the trip planner is not reachable at {url}"
    assert time.monotonic() - started >= WAIT_S


def test_the_timestamp_of_the_period_is_what_the_trip_planner_is_asked(
    tmp_path: Path, otp_stub: OtpStub
) -> None:
    city = city_on(tmp_path, otp_stub.url)

    routes(city, tmp_path / "w")

    assert otp_stub.queried_at
    assert {(item["date"], item["time"]) for item in otp_stub.queried_at} == {
        (city.period.routing_date.isoformat(), f"{city.period.routing_time:%H:%M:%S}")
    }


def routes_variant(order: list[int], target: Path) -> Path:
    """The committed routes with `od_results` in `order`, unsorted, as threads can leave them."""
    payload = json.loads((FIXTURES / "od_routes.json").read_text(encoding="utf-8"))
    payload["od_results"] = [payload["od_results"][index] for index in order]
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def instance_for(city: City, folder: Path, payload: dict[str, Any]) -> bytes:
    hubs_folder(city, folder)
    (folder / "od_routes.json").write_text(json.dumps(payload), encoding="utf-8")
    (folder / "od_geometry.json").write_bytes((FIXTURES / "od_geometry.json").read_bytes())
    outcome = city.prepare(folder, StepName.TRAVELLERS_AND_BIKES, NEVER, seed=1)
    assert outcome.failure_code is None, outcome.failure_reason
    return (folder / "Instance_1.json").read_bytes()


def test_the_same_seed_gives_the_same_travellers_only_for_a_sorted_file(tmp_path: Path) -> None:
    city = make_city(tmp_path / "data", None, FIXTURES / "gbfs_station_information.json")
    orders = {}
    for name, order in (("a", [0, 1]), ("b", [1, 0])):
        variant = routes_variant(order, tmp_path / f"{name}.json")
        orders[name] = json.loads(variant.read_text(encoding="utf-8"))

    unsorted_a = instance_for(city, tmp_path / "ua", orders["a"])
    unsorted_b = instance_for(city, tmp_path / "ub", orders["b"])
    sorted_a = instance_for(city, tmp_path / "sa", sorted_routes(orders["a"]))
    sorted_b = instance_for(city, tmp_path / "sb", sorted_routes(orders["b"]))

    assert unsorted_a != unsorted_b
    assert sorted_a == sorted_b
