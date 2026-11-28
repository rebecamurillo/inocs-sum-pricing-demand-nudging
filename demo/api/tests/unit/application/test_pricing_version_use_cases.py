import pytest

from pricing_demo.application.use_cases.create_pricing_version import CreatePricingVersion
from pricing_demo.application.use_cases.delete_city_instance import DeleteCityInstance
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.delete_pricing_version import DeletePricingVersion
from pricing_demo.application.use_cases.get_pricing_version import GetPricingVersion
from pricing_demo.application.use_cases.list_pricing_versions import ListPricingVersions
from pricing_demo.application.use_cases.update_pricing_version import UpdatePricingVersion
from pricing_demo.domain.builds import RunActive
from pricing_demo.domain.city_instances import InstanceVersionNotFound, VersionSealed
from pricing_demo.domain.pricing_versions import (
    HasPricingVersions,
    InstanceNotBuilt,
    IsShowcase,
    PricingVersionNotFound,
    UnknownBasedOn,
)
from pricing_demo.domain.runs import RunState
from tests.support.builds import MemoryBuilds
from tests.support.pricing_versions import built_in_memory, sealed_pricing_version

VERSION = "geneva-3km.v1"


class Rig:
    def __init__(self, build_state: RunState | None = RunState.SUCCEEDED) -> None:
        self.rig = MemoryBuilds()
        if build_state is None:
            self.rig.add_draft()
        else:
            built_in_memory(self.rig, build_state)
        args = (self.rig.instances, self.rig.pricing)
        self.create = CreatePricingVersion(
            self.rig.instances, self.rig.builds, self.rig.pricing, self.rig.clock
        )
        self.list = ListPricingVersions(*args)
        self.get = GetPricingVersion(*args)
        self.update = UpdatePricingVersion(*args)
        self.delete = DeletePricingVersion(self.rig.pricing)


def test_a_draft_takes_the_next_letter_and_the_defaults() -> None:
    rig = Rig()

    first = rig.create.execute(VERSION, None, None)
    second = rig.create.execute(VERSION, "Cheaper", None)

    assert (first.version.id, first.version.letter, first.version.name) == (
        "geneva-3km.v1.A",
        "A",
        "Version A",
    )
    assert (second.version.letter, second.version.name) == ("B", "Cheaper")
    assert first.state == "draft"
    assert (first.version.goals.cost_bike_chf, first.version.goals.ridership_weight) == (0.6, 8.0)
    assert [period.id for period in first.periods] == ["geneva-3km.v1.mon-08"]
    assert all(rule.passed for rule in first.rules)


def test_a_letter_is_not_reused_after_a_deletion() -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    rig.create.execute(VERSION, None, None)

    rig.delete.execute("geneva-3km.v1.B")

    assert rig.create.execute(VERSION, None, None).version.letter == "C"


@pytest.mark.parametrize("state", [None, RunState.QUEUED, RunState.RUNNING, RunState.FAILED])
def test_an_instance_version_that_is_not_built_refuses_a_draft(state: RunState | None) -> None:
    rig = Rig(state)

    with pytest.raises(InstanceNotBuilt):
        rig.create.execute(VERSION, None, None)


def test_an_unknown_instance_version_is_refused() -> None:
    with pytest.raises(InstanceVersionNotFound):
        Rig().create.execute("nope.v1", None, None)


def test_a_new_draft_keeps_four_values_of_the_last_sealed_version() -> None:
    rig = Rig()
    first = rig.create.execute(VERSION, None, None)
    rig.update.execute(first.version.id, {"pt_fare_chf": 2.4, "max_displayed_options": 3})
    sealed_pricing_version(rig.rig, first.version.id, RunState.SUCCEEDED)

    second = rig.create.execute(VERSION, None, None)

    assert (second.version.goals.pt_fare_chf, second.version.goals.max_displayed_options) == (
        2.4,
        3,
    )


def test_based_on_copies_the_goals_and_records_the_source() -> None:
    rig = Rig()
    first = rig.create.execute(VERSION, None, None)
    rig.update.execute(first.version.id, {"ridership_weight": 5.0, "flat_price_per_ride_chf": 1.7})
    sealed_pricing_version(rig.rig, first.version.id, RunState.SUCCEEDED)

    copy = rig.create.execute(VERSION, None, first.version.id)

    assert copy.version.goals == rig.rig.pricing.get(first.version.id).goals  # type: ignore[union-attr]
    assert copy.version.based_on_id == first.version.id
    assert copy.version.status == "draft"


def test_based_on_must_be_a_pricing_version_of_the_same_instance_version() -> None:
    rig = Rig()

    with pytest.raises(UnknownBasedOn):
        rig.create.execute(VERSION, None, "geneva-3km.v1.Z")


def test_a_change_is_stored_as_sent_and_every_broken_rule_named() -> None:
    rig = Rig()
    draft = rig.create.execute(VERSION, None, None)

    view = rig.update.execute(draft.version.id, {"cost_bike_chf": -1, "max_displayed_options": 0})

    assert view.version.goals.cost_bike_chf == -1
    assert [rule.message for rule in view.rules if not rule.passed] == [
        "Cost of one ride must be 0 or more: now -1",
        "Options shown per hub pair must be at least 1: now 0",
    ]


def test_a_sealed_version_cannot_change() -> None:
    rig = Rig()
    draft = rig.create.execute(VERSION, None, None)
    sealed_pricing_version(rig.rig, draft.version.id, RunState.QUEUED)

    with pytest.raises(VersionSealed):
        rig.update.execute(draft.version.id, {"cost_bike_chf": 1})


def test_an_unknown_pricing_version_is_refused() -> None:
    rig = Rig()

    for call in (rig.get.execute, rig.delete.execute):
        with pytest.raises(PricingVersionNotFound):
            call("geneva-3km.v1.A")
    with pytest.raises(PricingVersionNotFound):
        rig.update.execute("geneva-3km.v1.A", {})


@pytest.mark.parametrize(
    ("run", "state"),
    [
        (RunState.QUEUED, "queued"),
        (RunState.RUNNING, "running"),
        (RunState.FAILED, "failed"),
        (RunState.CANCELLED, "cancelled"),
        (RunState.SUCCEEDED, "result"),
    ],
)
def test_the_state_follows_the_last_run(run: RunState, state: str) -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    draft = rig.create.execute(VERSION, None, None)
    sealed_pricing_version(rig.rig, draft.version.id, run)

    assert rig.get.execute(draft.version.id).state == state
    assert [view.state for view in rig.list.execute(VERSION)] == ["draft", state]


def test_the_list_needs_an_instance_version() -> None:
    with pytest.raises(InstanceVersionNotFound):
        Rig().list.execute("nope.v1")


def test_a_draft_is_discarded() -> None:
    rig = Rig()
    draft = rig.create.execute(VERSION, None, None)

    rig.delete.execute(draft.version.id)

    assert rig.list.execute(VERSION) == []


def test_a_pricing_version_with_an_active_run_is_not_deleted() -> None:
    rig = Rig()
    draft = rig.create.execute(VERSION, None, None)
    sealed_pricing_version(rig.rig, draft.version.id, RunState.RUNNING)

    with pytest.raises(RunActive):
        rig.delete.execute(draft.version.id)


def test_an_instance_version_with_pricing_versions_is_deleted_only_when_they_go_too() -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    rig.create.execute(VERSION, None, None)
    delete_version = DeleteInstanceVersion(rig.rig.builds, rig.rig.showcase)

    with pytest.raises(HasPricingVersions) as refused:
        delete_version.execute(VERSION)
    assert refused.value.pricing_version_ids == ("geneva-3km.v1.A", "geneva-3km.v1.B")

    delete_version.execute(VERSION, True)
    assert rig.rig.instances.get_version(VERSION) is None
    assert rig.rig.pricing.get("geneva-3km.v1.A") is None


def test_a_city_instance_with_pricing_versions_is_deleted_only_when_they_go_too() -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    delete_instance = DeleteCityInstance(rig.rig.builds, rig.rig.showcase)

    with pytest.raises(HasPricingVersions):
        delete_instance.execute("geneva-3km")

    delete_instance.execute("geneva-3km", True)
    assert rig.rig.instances.get_instance("geneva-3km") is None


def test_an_active_pricing_run_refuses_a_deletion_even_with_the_flag() -> None:
    rig = Rig()
    draft = rig.create.execute(VERSION, None, None)
    sealed_pricing_version(rig.rig, draft.version.id, RunState.QUEUED)

    with pytest.raises(RunActive):
        DeleteInstanceVersion(rig.rig.builds, rig.rig.showcase).execute(VERSION, True)


def _showcased(rig: Rig, pricing_version_id: str = "geneva-3km.v1.A") -> None:
    rig.rig.showcase.mark(pricing_version_id, "geneva-3km.v1.mon-08", rig.rig.clock.now())


@pytest.mark.parametrize("including", [False, True])
def test_the_instance_version_holding_the_showcase_is_not_deleted(including: bool) -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    _showcased(rig)

    with pytest.raises(IsShowcase) as refused:
        DeleteInstanceVersion(rig.rig.builds, rig.rig.showcase).execute(VERSION, including)

    assert refused.value.version_id == "geneva-3km.v1.A"
    assert rig.rig.instances.get_version(VERSION) is not None
    assert rig.rig.pricing.get("geneva-3km.v1.A") is not None


@pytest.mark.parametrize("including", [False, True])
def test_the_city_instance_holding_the_showcase_is_not_deleted(including: bool) -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    _showcased(rig)

    with pytest.raises(IsShowcase):
        DeleteCityInstance(rig.rig.builds, rig.rig.showcase).execute("geneva-3km", including)

    assert rig.rig.instances.get_instance("geneva-3km") is not None
    assert rig.rig.pricing.get("geneva-3km.v1.A") is not None


def test_the_showcase_refusal_comes_before_the_active_run_refusal() -> None:
    rig = Rig()
    draft = rig.create.execute(VERSION, None, None)
    sealed_pricing_version(rig.rig, draft.version.id, RunState.RUNNING)
    _showcased(rig, draft.version.id)

    with pytest.raises(IsShowcase):
        DeleteInstanceVersion(rig.rig.builds, rig.rig.showcase).execute(VERSION, True)
    with pytest.raises(IsShowcase):
        DeleteCityInstance(rig.rig.builds, rig.rig.showcase).execute("geneva-3km")


def test_another_instance_version_or_instance_is_not_refused_for_the_showcase() -> None:
    rig = Rig()
    rig.create.execute(VERSION, None, None)
    _showcased(rig, "other-city.v1.A")

    DeleteInstanceVersion(rig.rig.builds, rig.rig.showcase).execute(VERSION, True)
    assert rig.rig.instances.get_version(VERSION) is None

    other = Rig()
    other.create.execute(VERSION, None, None)
    _showcased(other, "other-city.v1.A")
    DeleteCityInstance(other.rig.builds, other.rig.showcase).execute("geneva-3km", True)
    assert other.rig.instances.get_instance("geneva-3km") is None
