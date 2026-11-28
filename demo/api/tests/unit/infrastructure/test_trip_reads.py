"""The failures a version reads are those of the routes artefact it links, even when another
version's run produced that artefact (a kept step), whose failures carry that version's period."""

from pathlib import Path

from pricing_demo.domain.city_instances import first_period
from pricing_demo.infrastructure.fakes.trip_reads import InMemoryTripReads
from tests.support.builds import SLUG, MemoryBuilds, build_fake_city
from tests.support.trips import ROUTE_FAILURES

FIRST = f"{SLUG}.v1"
SECOND = f"{SLUG}.v2"


def test_a_version_that_kept_the_routes_of_another_reads_their_failures(tmp_path: Path) -> None:
    rig = MemoryBuilds()
    rig.add_draft()
    build_fake_city(rig, tmp_path, ROUTE_FAILURES)
    first = rig.instances.get_version(FIRST)
    dataset = rig.datasets.get("geneva-2026-11-26")
    assert first is not None
    assert dataset is not None
    rig.instances.create_draft(
        SLUG, FIRST, first.parameters, rig.clock.now(), lambda draft: first_period(draft, dataset)
    )
    (period,) = rig.instances.periods_of(SECOND)
    for step, key in rig.artifacts.links_of(FIRST).items():
        rig.artifacts.link(SECOND, step, period.id, key)
    reads = InMemoryTripReads(
        rig.instances, rig.datasets, rig.artifacts, rig.read_model, rig.route_failures
    )

    found = reads.pair_failures(SECOND, "H1", "H6")

    assert [(item.query, item.kind) for item in found] == [("pt_bike", "no_route")]
