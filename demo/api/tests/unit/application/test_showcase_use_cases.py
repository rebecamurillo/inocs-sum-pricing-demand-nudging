from pathlib import Path

import pytest

from pricing_demo.domain.pricing_versions import (
    IsShowcase,
    NoResult,
    NoShowcase,
    PricingVersionNotFound,
    ResultNotFound,
)
from tests.support.results import PERIOD, ResultRig


@pytest.fixture
def rig(tmp_path: Path) -> ResultRig:
    return ResultRig(tmp_path)


def test_nothing_is_showcased_at_first(rig: ResultRig) -> None:
    with pytest.raises(NoShowcase):
        rig.get_showcase.execute()


def test_a_finished_version_is_marked_and_read_back_with_its_headline_numbers(
    rig: ResultRig,
) -> None:
    version = rig.finished()

    mark = rig.mark.execute(version)
    view = rig.get_showcase.execute()

    assert (mark.pricing_version_id, mark.period_id) == (version, PERIOD)
    assert view.mark == mark
    assert view.letter == "A"
    assert view.instance_version_id == "geneva-3km.v1"
    assert view.instance_version_name == "Geneva 3 km v1"
    assert view.headline["ridership"].source == "model"
    assert {item.group for item in view.headline.values()} == {"headline"}
    assert view.headline == rig.result.execute(version).headline


def test_a_new_mark_replaces_the_old_one(rig: ResultRig) -> None:
    first = rig.finished()
    second = rig.finished(flat_price_per_ride_chf=2.5)
    rig.mark.execute(first)

    rig.mark.execute(second)

    assert rig.get_showcase.execute().mark.pricing_version_id == second


def test_a_version_without_a_result_cannot_be_marked(rig: ResultRig) -> None:
    draft = rig.version()

    with pytest.raises(NoResult):
        rig.mark.execute(draft)
    assert rig.rig.showcase.current() is None


def test_a_period_the_version_does_not_price_cannot_be_marked(rig: ResultRig) -> None:
    version = rig.finished()

    with pytest.raises(NoResult):
        rig.mark.execute(version, "geneva-3km.v1.tue-08")


def test_an_unknown_version_cannot_be_marked(rig: ResultRig) -> None:
    with pytest.raises(PricingVersionNotFound):
        rig.mark.execute("geneva-3km.v1.Z")


def test_the_showcased_version_is_not_deleted_and_another_is(rig: ResultRig) -> None:
    first, second = rig.finished(), rig.finished(flat_price_per_ride_chf=2.5)
    rig.mark.execute(first)

    with pytest.raises(IsShowcase):
        rig.rig.pricing.delete(first)
    rig.rig.pricing.delete(second)

    assert rig.rig.pricing.get(first) is not None
    assert rig.rig.pricing.get(second) is None


def test_a_marked_version_that_lost_a_part_of_its_result_is_not_returned_as_showcase(
    rig: ResultRig,
) -> None:
    version = rig.finished()
    rig.mark.execute(version)
    rig.rig.solves._summaries.clear()

    with pytest.raises(ResultNotFound):
        rig.get_showcase.execute()
