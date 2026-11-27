from collections.abc import Callable, Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pricing_demo.application.errors import ComponentNotControllable
from pricing_demo.application.result_lookup import ResultLookup
from pricing_demo.application.step_durations import StepDurations
from pricing_demo.application.use_cases.cancel_run import CancelRun
from pricing_demo.application.use_cases.create_city_instance import CreateCityInstance
from pricing_demo.application.use_cases.create_instance_version import CreateInstanceVersion
from pricing_demo.application.use_cases.create_pricing_version import CreatePricingVersion
from pricing_demo.application.use_cases.delete_city_instance import DeleteCityInstance
from pricing_demo.application.use_cases.delete_instance_version import DeleteInstanceVersion
from pricing_demo.application.use_cases.delete_pricing_version import DeletePricingVersion
from pricing_demo.application.use_cases.get_instance_version import GetInstanceVersion
from pricing_demo.application.use_cases.get_pricing_result import GetPricingResult
from pricing_demo.application.use_cases.get_pricing_version import GetPricingVersion
from pricing_demo.application.use_cases.get_run import GetRun
from pricing_demo.application.use_cases.get_run_log import GetRunLog
from pricing_demo.application.use_cases.get_showcase import GetShowcase
from pricing_demo.application.use_cases.get_system_status import GetSystemStatus
from pricing_demo.application.use_cases.list_city_datasets import ListCityDatasets
from pricing_demo.application.use_cases.list_city_instances import ListCityInstances
from pricing_demo.application.use_cases.list_hub_pair_results import ListHubPairResults
from pricing_demo.application.use_cases.list_hub_pairs import ListHubPairs
from pricing_demo.application.use_cases.list_hub_results import ListHubResults
from pricing_demo.application.use_cases.list_hubs import ListHubs
from pricing_demo.application.use_cases.list_pricing_versions import ListPricingVersions
from pricing_demo.application.use_cases.list_route_failures import ListRouteFailures
from pricing_demo.application.use_cases.list_route_pairs import ListRoutePairs
from pricing_demo.application.use_cases.list_runs import ListRuns
from pricing_demo.application.use_cases.list_stations import ListStations
from pricing_demo.application.use_cases.mark_showcase import MarkShowcase
from pricing_demo.application.use_cases.report_components import ReportComponents
from pricing_demo.application.use_cases.update_instance_version import UpdateInstanceVersion
from pricing_demo.application.use_cases.update_pricing_version import UpdatePricingVersion
from pricing_demo.domain.city_datasets import GENEVA_SLUG, dataset_id_for
from pricing_demo.domain.system_status import (
    PROBED_COMPONENTS,
    ComponentName,
    ComponentState,
    ComponentStatus,
)
from pricing_demo.infrastructure.fakes.city_datasets import InMemoryCityDatasets, fake_city_dataset
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.component_probe import FakeProbe, fixed_probe
from pricing_demo.infrastructure.fakes.component_reports import InMemoryComponentReports
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.package_fingerprints import (
    FAKE_FINGERPRINT,
    InMemoryPackageFingerprints,
)
from pricing_demo.infrastructure.fakes.route_failures import InMemoryRouteFailures
from pricing_demo.interface.http.app import create_app
from pricing_demo.interface.http.routers.city_datasets import build_city_datasets_router
from pricing_demo.interface.http.routers.city_instances import build_city_instances_router
from pricing_demo.interface.http.routers.comparisons import build_comparisons_router
from pricing_demo.interface.http.routers.pricing_versions import build_pricing_versions_router
from pricing_demo.interface.http.routers.runs import build_runs_router
from pricing_demo.interface.http.routers.showcase import build_showcase_router
from pricing_demo.interface.http.routers.system_status import build_system_status_router
from pricing_demo.interface.http.routers.test_control import build_test_control_router
from tests.support.builds import FINGERPRINT, MemoryBuilds
from tests.support.results import ResultRig
from tests.support.runs import later

API_VERSION = "0.1.0"
SERVER_TIME = later(100)

AppFactory = Callable[[GetSystemStatus], TestClient]


class MemorySeam:
    """The test-control seam on in-memory settings, with the rules of the real one."""

    def __init__(
        self, settings: InMemoryFakeSettings, datasets: InMemoryCityDatasets, clock: FixedClock
    ) -> None:
        self.settings = settings
        self.datasets = datasets
        self.clock = clock

    def set_component(self, name: ComponentName, state: ComponentState, reason: str | None) -> None:
        if name not in PROBED_COMPONENTS:
            raise ComponentNotControllable(f"The {name} component is not faked.")
        ComponentStatus(name, state, reason)
        self.settings.set_component(name.value, state.value, reason)

    def insert_city_dataset(self) -> str:
        now = self.clock.now()
        prefix = f"{GENEVA_SLUG}-{now.date().isoformat()}"
        dataset_id = dataset_id_for(
            GENEVA_SLUG, now.date(), self.datasets.ids_starting_with(prefix)
        )
        self.datasets.add(fake_city_dataset(dataset_id, now))
        return dataset_id

    def set_pricing_model(self, settings: Mapping[str, object]) -> None:
        self.settings.set_pricing_model(settings)

    def release_run(self, run_id: str) -> None:
        self.settings.release_run(run_id)

    def reset(self) -> None:
        self.settings.write_defaults()
        self.datasets.clear()


class Faked:
    """An app built from fakes. `worker_reports()` does what the worker does at each cycle:
    its fake probes read the settings the test-control routes wrote and report them."""

    def __init__(self, with_city_data: bool = True) -> None:
        self.settings = InMemoryFakeSettings()
        self.reports = InMemoryComponentReports()
        self.clock = FixedClock(SERVER_TIME)
        self.datasets = InMemoryCityDatasets()
        if with_city_data:
            self.datasets.add(fake_city_dataset("geneva-2026-11-26", SERVER_TIME))
        self.reports.worker_heartbeats["w-1"] = SERVER_TIME
        self.use_case = GetSystemStatus(
            fixed_probe(ComponentStatus.ready(ComponentName.STORAGE)),
            self.reports,
            self.datasets,
            self.clock,
        )
        self._report = ReportComponents(
            [FakeProbe(name, self.settings) for name in PROBED_COMPONENTS],
            self.reports,
            "w-1",
            self.clock,
        )
        self.report_cycle()
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[
                    build_system_status_router(self.use_case),
                    build_city_datasets_router(ListCityDatasets(self.datasets)),
                ],
                test_control=build_test_control_router(
                    MemorySeam(self.settings, self.datasets, self.clock)
                ),
            ),
            raise_server_exceptions=False,
        )

    def report_cycle(self) -> None:
        self._report.execute()


@pytest.fixture
def faked() -> Faked:
    return Faked()


@pytest.fixture
def faked_without_city_data() -> Faked:
    return Faked(with_city_data=False)


@pytest.fixture
def client_for() -> AppFactory:
    """A client for an app whose use case is the one given."""

    def build(use_case: GetSystemStatus) -> TestClient:
        return TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[build_system_status_router(use_case)],
            ),
            raise_server_exceptions=False,
        )

    return build


class RunsApp:
    """An app with the run routes on an in-memory repository and a fixed clock."""

    def __init__(self) -> None:
        self.rig = MemoryBuilds()
        self.rig.pricing.read_durations_from(self.rig.instances)
        self.repository = self.rig.runs
        self.route_failures = InMemoryRouteFailures()
        self.clock = FixedClock(SERVER_TIME)
        durations = StepDurations(self.rig.pricing, self.rig.instances)
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[
                    build_runs_router(
                        ListRuns(self.repository, self.clock, durations),
                        GetRun(self.repository, self.clock, durations),
                        GetRunLog(self.repository),
                        CancelRun(self.repository, self.clock, durations),
                        ListRouteFailures(self.repository, self.route_failures),
                    )
                ],
            ),
            raise_server_exceptions=False,
        )


@pytest.fixture
def runs_app() -> RunsApp:
    return RunsApp()


class CityInstancesApp:
    """An app with the city instance routes on in-memory adapters, a data set
    `geneva-2026-11-26` and, unless told otherwise, a recorded package fingerprint (the
    worker's, for the build plan) and a trip planner manifest."""

    def __init__(self, with_fingerprint: bool = True) -> None:
        self.rig = MemoryBuilds(
            fingerprint=FINGERPRINT if with_fingerprint else None, now=SERVER_TIME
        )
        self.clock = self.rig.clock
        self.datasets = self.rig.datasets
        self.datasets.add(fake_city_dataset("geneva-2026-11-26", SERVER_TIME))
        self.instances = self.rig.instances
        self.runs = self.rig.runs
        self.status = self.rig.status
        self.fingerprints = InMemoryPackageFingerprints()
        if with_fingerprint:
            self.fingerprints.record(FAKE_FINGERPRINT, SERVER_TIME)
        planning = self.rig.planning
        built = self.rig.built
        lookup = ResultLookup(self.rig.pricing, self.rig.solves, self.rig.simulations)
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[
                    build_city_instances_router(
                        CreateCityInstance(
                            self.instances,
                            self.datasets,
                            self.fingerprints,
                            self.clock,
                            planning,
                            built,
                        ),
                        ListCityInstances(self.instances, self.rig.builds, self.rig.pricing),
                        CreateInstanceVersion(
                            self.instances,
                            self.datasets,
                            self.clock,
                            planning,
                            built,
                            self.fingerprints,
                        ),
                        GetInstanceVersion(
                            self.instances, self.datasets, planning, built, self.fingerprints
                        ),
                        UpdateInstanceVersion(
                            self.instances, self.datasets, planning, built, self.fingerprints
                        ),
                        DeleteInstanceVersion(self.rig.builds),
                        DeleteCityInstance(self.rig.builds),
                        self.rig.build,
                        GetRun(self.runs, self.clock),
                        ListStations(self.instances, self.rig.artifacts, self.rig.read_model),
                        ListHubs(self.instances, self.rig.artifacts, self.rig.read_model),
                        ListHubPairs(self.instances, self.rig.artifacts, self.rig.read_model),
                        ListRoutePairs(self.instances, self.rig.artifacts, self.rig.read_model),
                    ),
                    build_pricing_versions_router(
                        CreatePricingVersion(
                            self.instances, self.rig.builds, self.rig.pricing, self.clock
                        ),
                        ListPricingVersions(self.instances, self.rig.pricing),
                        GetPricingVersion(self.instances, self.rig.pricing),
                        UpdatePricingVersion(self.instances, self.rig.pricing),
                        DeletePricingVersion(self.rig.pricing),
                        self.rig.run_pricing,
                        GetRun(self.runs, self.clock),
                        self.rig.simulate,
                        self.rig.list_simulations,
                        GetPricingResult(
                            lookup,
                            self.rig.simulations,
                            self.instances,
                            self.datasets,
                            self.rig.artifacts,
                            self.fingerprints,
                            self.rig.status,
                        ),
                        ListHubPairResults(
                            lookup, self.rig.solves, self.rig.artifacts, self.rig.read_model
                        ),
                        ListHubResults(lookup, self.rig.artifacts, self.rig.read_model),
                    ),
                    build_showcase_router(
                        MarkShowcase(lookup, self.rig.showcase, self.clock),
                        GetShowcase(self.rig.showcase, lookup, self.instances),
                    ),
                ],
            ),
            raise_server_exceptions=False,
        )


@pytest.fixture
def instances_app() -> CityInstancesApp:
    return CityInstancesApp()


class ResultsApp:
    """An app with the pricing version and showcase routes over a built fake city whose
    pricing versions the worker's two steps have run."""

    def __init__(self, folder: Path) -> None:
        self.results = ResultRig(folder)
        rig = self.results.rig
        clock = rig.clock
        self.client = TestClient(
            create_app(
                api_version=API_VERSION,
                routers=[
                    build_pricing_versions_router(
                        CreatePricingVersion(rig.instances, rig.builds, rig.pricing, clock),
                        ListPricingVersions(rig.instances, rig.pricing),
                        GetPricingVersion(rig.instances, rig.pricing),
                        UpdatePricingVersion(rig.instances, rig.pricing),
                        DeletePricingVersion(rig.pricing),
                        rig.run_pricing,
                        GetRun(rig.runs, clock),
                        rig.simulate,
                        rig.list_simulations,
                        self.results.result,
                        self.results.hub_pairs,
                        self.results.hubs,
                    ),
                    build_comparisons_router(self.results.compare),
                    build_showcase_router(self.results.mark, self.results.get_showcase),
                ],
            ),
            raise_server_exceptions=False,
        )


@pytest.fixture
def results_app(tmp_path: Path) -> ResultsApp:
    return ResultsApp(tmp_path)
