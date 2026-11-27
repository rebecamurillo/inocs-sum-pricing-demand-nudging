from dataclasses import replace

import pytest

from pricing_demo.application.build_planning import BuildPlanning
from pricing_demo.application.built_counts import BuiltCounts
from pricing_demo.application.errors import (
    PackageDefaultsMissing,
    UnknownCityDataset,
    UnknownStartVersion,
)
from pricing_demo.application.instance_version_view import InstanceVersionView
from pricing_demo.application.use_cases.create_city_instance import (
    CreateCityInstance,
    FromCopy,
    FromPackageDefaults,
)
from pricing_demo.application.use_cases.create_instance_version import CreateInstanceVersion
from pricing_demo.application.use_cases.delete_city_instance import DeleteCityInstance
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.get_instance_version import GetInstanceVersion
from pricing_demo.application.use_cases.list_city_instances import ListCityInstances
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
from pricing_demo.domain.builds import RunActive
from pricing_demo.domain.city_instances import (
    CityInstanceNameTaken,
    CityInstanceNotFound,
    DraftExists,
    InstanceVersionNotFound,
    InvalidInstanceName,
    ParameterChange,
    VersionSealed,
)
from pricing_demo.domain.runs import RunState
from pricing_demo.infrastructure.fakes.artifacts import InMemoryArtifacts
from pricing_demo.infrastructure.fakes.build_sources import InMemoryBuildSources
from pricing_demo.infrastructure.fakes.builds import InMemoryBuilds
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from pricing_demo.infrastructure.fakes.city_instances import InMemoryCityInstances
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.package_fingerprints import (
    FAKE_FINGERPRINT,
    InMemoryPackageFingerprints,
)
from pricing_demo.infrastructure.fakes.pricing_versions import FakePricingVersions
from pricing_demo.infrastructure.fakes.read_model import InMemoryReadModel
from pricing_demo.infrastructure.fakes.route_failures import InMemoryRouteFailures
from pricing_demo.infrastructure.fakes.run_repository import InMemoryRunRepository
from tests.support.builds import all_available
from tests.support.runs import T0, make_run

DATASET_ID = "geneva-2026-11-26"


class Rig:
    def __init__(self, with_fingerprint: bool = True) -> None:
        self.clock = FixedClock(T0)
        self.datasets = InMemoryCityDatasets()
        self.datasets.add(fake_city_dataset(DATASET_ID, T0))
        self.instances = InMemoryCityInstances()
        self.fingerprints = InMemoryPackageFingerprints()
        if with_fingerprint:
            self.fingerprints.record(FAKE_FINGERPRINT, T0)
        self.runs = InMemoryRunRepository()
        builds = InMemoryBuilds(self.runs, self.instances)
        artifacts = InMemoryArtifacts()
        built = BuiltCounts(artifacts, InMemoryReadModel(), InMemoryRouteFailures())
        planning = BuildPlanning(
            self.instances,
            self.datasets,
            artifacts,
            InMemoryBuildSources(),
            builds,
            all_available,
        )
        self.create = CreateCityInstance(
            self.instances, self.datasets, self.fingerprints, self.clock, planning, built
        )
        self.create_version = CreateInstanceVersion(
            self.instances, self.datasets, self.clock, planning, built, self.fingerprints
        )
        self.update = UpdateInstanceVersion(
            self.instances, self.datasets, planning, built, self.fingerprints
        )
        self.get = GetInstanceVersion(
            self.instances, self.datasets, planning, built, self.fingerprints
        )
        self.delete = DeleteInstanceVersion(builds)
        self.delete_instance = DeleteCityInstance(builds)
        self.menu = ListCityInstances(self.instances, builds, FakePricingVersions(self.runs))

    def geneva(self) -> InstanceVersionView:
        return self.create.execute("Geneva 3 km", DATASET_ID, FromPackageDefaults())


def test_an_instance_is_created_with_its_first_draft_and_period() -> None:
    rig = Rig()

    view = rig.geneva()

    assert view.version.id == "geneva-3km.v1"
    assert (view.version.status, view.version.based_on_id, view.state) == ("draft", None, "draft")
    assert view.version.parameters.seed == 42
    assert view.version.parameters.radius_m == 3000
    assert [period.id for period in view.periods] == ["geneva-3km.v1.mon-08"]
    assert view.changes == ()
    # The package's own defaults tie the trip distance and the grouping distance at 500 m.
    assert [rule.rule for rule in view.rules if not rule.passed] == [
        "min_trip_distance_above_grouping"
    ]
    instance = rig.instances.get_instance("geneva-3km")
    assert instance is not None
    assert (instance.name, instance.dataset_id, instance.next_number) == (
        "Geneva 3 km",
        DATASET_ID,
        2,
    )


def test_a_copy_takes_every_parameter_of_the_version_and_is_based_on_it() -> None:
    rig = Rig()
    first = rig.geneva()
    rig.update.execute(first.version.id, {"radius_m": 4000, "seed": 7})

    copy = rig.create.execute("Geneva 4 km", DATASET_ID, FromCopy("geneva-3km.v1"))

    assert copy.version.id == "geneva-4km.v1"
    assert copy.version.based_on_id == "geneva-3km.v1"
    assert copy.version.parameters.radius_m == 4000
    assert copy.version.parameters.seed == 7
    assert copy.changes == ()


def test_a_used_name_or_slug_is_refused() -> None:
    rig = Rig()
    rig.geneva()

    for name in ("Geneva 3 km", "geneva 3km", "GENEVA-3KM"):
        with pytest.raises(CityInstanceNameTaken):
            rig.create.execute(name, DATASET_ID, FromPackageDefaults())


def test_a_name_without_letters_is_refused() -> None:
    with pytest.raises(InvalidInstanceName):
        Rig().create.execute("***", DATASET_ID, FromPackageDefaults())


def test_an_unknown_data_set_or_start_version_is_refused() -> None:
    rig = Rig()

    with pytest.raises(UnknownCityDataset):
        rig.create.execute("A", "nope", FromPackageDefaults())
    with pytest.raises(UnknownStartVersion):
        rig.create.execute("A", DATASET_ID, FromCopy("nope.v1"))
    assert rig.menu.execute() == []


def test_the_package_defaults_need_a_recorded_fingerprint() -> None:
    rig = Rig(with_fingerprint=False)

    with pytest.raises(PackageDefaultsMissing):
        rig.geneva()


def test_a_second_draft_is_refused_and_names_the_first() -> None:
    rig = Rig()
    rig.geneva()

    with pytest.raises(DraftExists) as raised:
        rig.create_version.execute("geneva-3km", "geneva-3km.v1")

    assert raised.value.draft_id == "geneva-3km.v1"


def test_a_new_draft_takes_the_next_number_and_a_discarded_number_is_never_reused() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)

    second = rig.create_version.execute("geneva-3km", "geneva-3km.v1")
    rig.delete.execute(second.version.id)
    third = rig.create_version.execute("geneva-3km", "geneva-3km.v1")

    assert (second.version.id, third.version.id) == ("geneva-3km.v2", "geneva-3km.v3")
    assert third.version.based_on_id == "geneva-3km.v1"
    assert [period.id for period in third.periods] == ["geneva-3km.v3.mon-08"]


def test_a_draft_of_an_unknown_instance_or_base_is_refused() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)

    with pytest.raises(CityInstanceNotFound):
        rig.create_version.execute("nope", "geneva-3km.v1")
    with pytest.raises(UnknownStartVersion):
        rig.create_version.execute("geneva-3km", "geneva-3km.v9")


def test_an_update_stores_the_values_as_sent_and_reports_the_rules() -> None:
    rig = Rig()
    rig.geneva()

    view = rig.update.execute("geneva-3km.v1", {"seed": 1.5, "radius_m": 6000})

    assert (view.version.parameters.seed, view.version.parameters.radius_m) == (1.5, 6000)
    failed = {rule.rule for rule in view.rules if not rule.passed}
    assert failed == {
        "min_trip_distance_above_grouping",
        "seed_whole_number",
        "radius_1_to_5_km",
    }
    assert rig.get.execute("geneva-3km.v1").version.parameters.seed == 1.5


def test_what_changes_is_against_the_version_it_is_based_on() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)
    rig.create_version.execute("geneva-3km", "geneva-3km.v1")

    view = rig.update.execute("geneva-3km.v2", {"fixed_capacity": 25})

    assert view.changes == (ParameterChange("fixed_capacity", 20, 25),)


def test_a_sealed_version_is_not_updated() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)

    with pytest.raises(VersionSealed):
        rig.update.execute("geneva-3km.v1", {"seed": 1})


def test_a_sealed_version_is_deleted_with_its_runs() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)
    rig.runs.add(make_run("r1", subject_id="geneva-3km.v1", state=RunState.FAILED))

    rig.delete.execute("geneva-3km.v1")

    assert rig.instances.get_version("geneva-3km.v1") is None
    assert rig.runs.get("r1") is None


def test_a_version_with_an_active_run_is_not_deleted() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)
    rig.runs.add(make_run("r1", subject_id="geneva-3km.v1", state=RunState.RUNNING))

    with pytest.raises(RunActive):
        rig.delete.execute("geneva-3km.v1")

    assert rig.instances.get_version("geneva-3km.v1") is not None


def test_an_instance_is_deleted_with_all_its_versions() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)
    rig.create_version.execute("geneva-3km", "geneva-3km.v1")

    rig.delete_instance.execute("geneva-3km")

    assert rig.menu.execute() == []


def test_an_instance_with_an_active_run_on_any_version_is_not_deleted() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)
    rig.create_version.execute("geneva-3km", "geneva-3km.v1")
    rig.runs.add(make_run("r1", subject_id="geneva-3km.v1", state=RunState.QUEUED))

    with pytest.raises(RunActive):
        rig.delete_instance.execute("geneva-3km")

    assert len(rig.menu.execute()[0].versions) == 2


def test_an_unknown_instance_is_not_found_when_deleted() -> None:
    with pytest.raises(CityInstanceNotFound):
        Rig().delete_instance.execute("x")


def test_an_unknown_version_is_not_found() -> None:
    rig = Rig()

    for call in (
        lambda: rig.get.execute("x.v1"),
        lambda: rig.update.execute("x.v1", {}),
        lambda: rig.delete.execute("x.v1"),
    ):
        with pytest.raises(InstanceVersionNotFound):
            call()


def test_discarding_the_only_version_deletes_the_instance() -> None:
    rig = Rig()
    rig.geneva()

    rig.delete.execute("geneva-3km.v1")

    assert rig.menu.execute() == []
    assert rig.instances.get_instance("geneva-3km") is None


def test_discarding_a_draft_keeps_an_instance_that_has_other_versions() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)
    rig.create_version.execute("geneva-3km", "geneva-3km.v1")

    rig.delete.execute("geneva-3km.v2")

    (entry,) = rig.menu.execute()
    assert [version.id for version in entry.versions] == ["geneva-3km.v1"]


def test_the_menu_lists_instances_with_their_versions_by_number() -> None:
    rig = Rig()
    rig.geneva()
    rig.create.execute("Lyon", DATASET_ID, FromPackageDefaults())

    menu = rig.menu.execute()

    assert [entry.instance.id for entry in menu] == ["geneva-3km", "lyon"]
    assert [version.number for version in menu[0].versions] == [1]
    assert replace(menu[0].versions[0], parameters=menu[0].versions[0].parameters).status == "draft"


def test_a_draft_carries_the_package_defaults_and_its_creation_instant() -> None:
    rig = Rig()

    view = rig.geneva()

    assert view.version.created_at == T0
    # The values a new instance from the package defaults starts with.
    assert view.package_defaults == view.version.parameters
    edited = rig.update.execute(view.version.id, {"radius_m": 4000, "seed": 7})
    assert edited.package_defaults == view.package_defaults
    assert rig.get.execute(view.version.id).package_defaults == view.package_defaults


def test_a_second_draft_carries_the_package_defaults() -> None:
    rig = Rig()
    first = rig.geneva()
    rig.update.execute(first.version.id, {"radius_m": 4000})
    rig.instances.seal(first.version.id, T0)

    draft = rig.create_version.execute("geneva-3km", first.version.id)

    assert draft.version.parameters.radius_m == 4000
    assert draft.package_defaults is not None
    assert draft.package_defaults.radius_m == 3000


def test_a_sealed_version_has_no_package_defaults() -> None:
    rig = Rig()
    rig.geneva()
    rig.instances.seal("geneva-3km.v1", T0)

    assert rig.get.execute("geneva-3km.v1").package_defaults is None


def test_a_draft_has_no_package_defaults_while_no_package_is_recorded() -> None:
    rig = Rig()
    rig.geneva()
    rig.fingerprints.clear()

    assert rig.get.execute("geneva-3km.v1").package_defaults is None
