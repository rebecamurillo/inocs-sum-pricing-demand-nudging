from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.infrastructure.fakes.build_sources import InMemoryBuildSources
from tests.support.builds import FINGERPRINT
from tests.support.runs import T0
from tests.unit.application.test_run_build_step import ROUTES, Rig, queued


def test_a_refused_routes_attempt_does_not_keep_an_earlier_attempts_failures() -> None:
    rig = Rig()
    rig.builds.sources = InMemoryBuildSources(FINGERPRINT, {"gtfs_sha256": "1" * 64})
    rig.executor = rig.builds.executor(rig.preparation, rig.files)
    run = queued(rig)
    earlier = RouteFailure("H1", "H2", "pt_bike", "technical", "earlier attempt", 4)
    rig.builds.route_failures.add(run.id, 3, "p", earlier, T0)

    outcome = rig.execute(run, ROUTES)

    assert outcome.failure_code == "timetable_mismatch"
    assert rig.builds.route_failures.of_step(run.id, 3) == []
