from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import pytest

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.system_status import (
    NO_CITY_DATA_REASON,
    NO_RUNNER_REASON,
    PROBED_COMPONENTS,
    STORAGE_UNKNOWN_REASON,
    BlockingReason,
    ComponentName,
    ComponentReport,
    ComponentState,
    ComponentStatus,
    IncompleteSystemStatus,
    InvalidComponentStatus,
    SystemStatus,
    build_verdict,
    system_status_from,
)

SOLVER_REASON = "No Gurobi licence was found."
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
ORDER = list(ComponentName)


def system_status(
    unavailable: Mapping[str, str] | None = None, limited: tuple[str, ...] = ()
) -> SystemStatus:
    """Every component available, except those named with their reason, or limited."""
    unavailable = unavailable or {}
    statuses = []
    for name in ComponentName:
        if name.value in unavailable:
            statuses.append(ComponentStatus.unavailable(name, unavailable[name.value]))
        elif name.value in limited:
            statuses.append(ComponentStatus.limited(name, f"{name.value} limited"))
        else:
            statuses.append(ComponentStatus.ready(name))
    return SystemStatus.of(statuses)


def test_the_components_are_the_six_of_the_lab_in_order() -> None:
    assert [name.value for name in ComponentName] == [
        "storage",
        "runner",
        "solver",
        "package",
        "trip_planner",
        "city_data",
    ]
    assert PROBED_COMPONENTS == (
        ComponentName.SOLVER,
        ComponentName.PACKAGE,
        ComponentName.TRIP_PLANNER,
    )


def test_an_available_component_has_no_reason() -> None:
    status = ComponentStatus.ready(ComponentName.STORAGE)

    assert status.state is ComponentState.AVAILABLE
    assert status.reason is None


def test_an_unavailable_component_keeps_its_reason() -> None:
    status = ComponentStatus.unavailable(ComponentName.SOLVER, SOLVER_REASON)

    assert status.state is ComponentState.UNAVAILABLE
    assert status.reason == SOLVER_REASON


def test_a_limited_solver_keeps_its_reason() -> None:
    status = ComponentStatus.limited(ComponentName.SOLVER, "Size-limited licence.")

    assert status.state is ComponentState.LIMITED
    assert status.reason == "Size-limited licence."


@pytest.mark.parametrize(
    "name", [name for name in ComponentName if name is not ComponentName.SOLVER]
)
def test_limited_is_a_state_of_the_solver_only(name: ComponentName) -> None:
    with pytest.raises(InvalidComponentStatus):
        ComponentStatus.limited(name, "limited")


@pytest.mark.parametrize("reason", [None, ""])
@pytest.mark.parametrize("state", [ComponentState.LIMITED, ComponentState.UNAVAILABLE])
def test_a_component_that_is_not_available_needs_a_reason(
    state: ComponentState, reason: str | None
) -> None:
    with pytest.raises(InvalidComponentStatus):
        ComponentStatus(ComponentName.SOLVER, state, reason)


def test_an_available_component_with_a_reason_is_refused() -> None:
    with pytest.raises(InvalidComponentStatus):
        ComponentStatus(ComponentName.STORAGE, ComponentState.AVAILABLE, "fine")


def test_a_status_error_is_a_domain_error() -> None:
    assert issubclass(InvalidComponentStatus, DomainError)


def test_a_system_status_lists_every_component_in_order() -> None:
    status = SystemStatus.of(reversed([ComponentStatus.ready(name) for name in ComponentName]))

    assert [item.name for item in status.components] == ORDER


def test_a_system_status_without_all_the_components_is_refused() -> None:
    with pytest.raises(IncompleteSystemStatus):
        SystemStatus.of([ComponentStatus.ready(ComponentName.STORAGE)])


def test_every_verdict_allows_when_every_component_is_available() -> None:
    status = system_status()

    for verdict in (status.can_build_instances, status.can_run_pricing, status.can_simulate):
        assert verdict.allowed
        assert verdict.reasons == ()


@pytest.mark.parametrize(
    ("down", "builds", "pricing", "simulations"),
    [
        ("storage", True, True, True),
        ("runner", True, True, True),
        ("solver", False, True, False),
        ("package", True, True, False),
        ("trip_planner", True, False, False),
        ("city_data", True, False, False),
    ],
)
def test_a_missing_component_refuses_the_verdicts_that_need_it(
    down: str, builds: bool, pricing: bool, simulations: bool
) -> None:
    status = system_status({down: f"{down} is down"})

    assert (status.can_build_instances.allowed is False) is builds
    assert (status.can_run_pricing.allowed is False) is pricing
    assert (status.can_simulate.allowed is False) is simulations
    for verdict in (status.can_build_instances, status.can_run_pricing, status.can_simulate):
        if not verdict.allowed:
            assert verdict.reasons == (BlockingReason(ComponentName(down), f"{down} is down"),)


def test_a_limited_solver_refuses_pricing_runs_only() -> None:
    status = system_status(limited=("solver",))

    assert not status.can_run_pricing.allowed
    assert status.can_run_pricing.reasons == (
        BlockingReason(ComponentName.SOLVER, "solver limited"),
    )
    assert status.can_build_instances.allowed
    assert status.can_simulate.allowed


def test_an_unavailable_solver_refuses_pricing_runs_only() -> None:
    status = system_status({"solver": SOLVER_REASON})

    assert not status.can_run_pricing.allowed
    assert status.can_build_instances.allowed
    assert status.can_simulate.allowed


def test_an_unavailable_trip_planner_refuses_builds_only() -> None:
    status = system_status({"trip_planner": "OTP is down"})

    assert not status.can_build_instances.allowed
    assert status.can_run_pricing.allowed
    assert status.can_simulate.allowed


def test_a_runner_that_is_down_refuses_all_three() -> None:
    status = system_status({"runner": "no runner"})

    assert not status.can_build_instances.allowed
    assert not status.can_run_pricing.allowed
    assert not status.can_simulate.allowed


def test_storage_down_refuses_all_three() -> None:
    status = system_status({"storage": "no database"})

    for verdict in (status.can_build_instances, status.can_run_pricing, status.can_simulate):
        assert not verdict.allowed
        assert verdict.reasons[0] == BlockingReason(ComponentName.STORAGE, "no database")


def test_reasons_come_in_component_order() -> None:
    status = system_status(
        {
            "storage": "s",
            "runner": "r",
            "solver": "v",
            "package": "p",
            "trip_planner": "t",
            "city_data": "c",
        }
    )

    assert [item.component for item in status.can_build_instances.reasons] == [
        ComponentName.STORAGE,
        ComponentName.RUNNER,
        ComponentName.PACKAGE,
        ComponentName.TRIP_PLANNER,
        ComponentName.CITY_DATA,
    ]
    assert [item.component for item in status.can_run_pricing.reasons] == [
        ComponentName.STORAGE,
        ComponentName.RUNNER,
        ComponentName.SOLVER,
        ComponentName.PACKAGE,
    ]
    assert [item.component for item in status.can_simulate.reasons] == [
        ComponentName.STORAGE,
        ComponentName.RUNNER,
    ]


# -- system_status_from ------------------------------------------------------------------


def report(
    name: ComponentName,
    *,
    heartbeat_age: float | None = 1,
    status: ComponentStatus | None = None,
) -> ComponentReport:
    heartbeat = None if heartbeat_age is None else NOW - timedelta(seconds=heartbeat_age)
    return ComponentReport(
        status=status or ComponentStatus.ready(name),
        reported_at=NOW,
        worker_id="w-1",
        worker_heartbeat_at=heartbeat,
        details={},
    )


def reports(**overrides: ComponentReport) -> list[ComponentReport]:
    return [overrides.get(name.value) or report(name) for name in PROBED_COMPONENTS]


STORAGE_OK = ComponentStatus.ready(ComponentName.STORAGE)
CITY_OK = ComponentStatus.ready(ComponentName.CITY_DATA)


def by_name(status: SystemStatus) -> dict[ComponentName, ComponentStatus]:
    return {item.name: item for item in status.components}


def test_fresh_reports_and_a_fresh_heartbeat_make_everything_available() -> None:
    status = system_status_from(STORAGE_OK, NOW - timedelta(seconds=2), reports(), NOW, CITY_OK)

    assert all(item.state is ComponentState.AVAILABLE for item in status.components)


def test_no_heartbeat_makes_the_runner_unavailable_with_its_reason() -> None:
    status = system_status_from(STORAGE_OK, None, [], NOW, CITY_OK)

    runner = by_name(status)[ComponentName.RUNNER]
    assert runner.state is ComponentState.UNAVAILABLE
    assert runner.reason == NO_RUNNER_REASON


@pytest.mark.parametrize(("age", "alive"), [(30, True), (30.001, False)])
def test_the_runner_is_alive_within_thirty_seconds_of_the_heartbeat(
    age: float, alive: bool
) -> None:
    status = system_status_from(STORAGE_OK, NOW - timedelta(seconds=age), reports(), NOW, CITY_OK)

    runner = by_name(status)[ComponentName.RUNNER]
    assert (runner.state is ComponentState.AVAILABLE) is alive


def test_a_probed_component_without_a_report_says_the_runner_has_not_reported_it() -> None:
    status = system_status_from(STORAGE_OK, NOW, [], NOW, CITY_OK)

    items = by_name(status)
    assert items[ComponentName.SOLVER].reason == "The runner has not reported the solver."
    assert items[ComponentName.PACKAGE].reason == "The runner has not reported the pricing package."
    assert (
        items[ComponentName.TRIP_PLANNER].reason == "The runner has not reported the trip planner."
    )
    assert items[ComponentName.SOLVER].state is ComponentState.UNAVAILABLE


@pytest.mark.parametrize("heartbeat_age", [30.001, None])
def test_a_report_of_a_worker_that_stopped_reporting_is_stale(heartbeat_age: float | None) -> None:
    status = system_status_from(
        STORAGE_OK,
        NOW,
        reports(solver=report(ComponentName.SOLVER, heartbeat_age=heartbeat_age)),
        NOW,
        CITY_OK,
    )

    items = by_name(status)
    assert items[ComponentName.SOLVER].state is ComponentState.UNAVAILABLE
    assert items[ComponentName.SOLVER].reason == "The runner has not reported the solver."
    assert items[ComponentName.PACKAGE].state is ComponentState.AVAILABLE


def test_a_fresh_report_is_used_as_it_is() -> None:
    limited = ComponentStatus.limited(ComponentName.SOLVER, "Size-limited licence.")
    down = ComponentStatus.unavailable(ComponentName.TRIP_PLANNER, "OTP does not answer.")

    status = system_status_from(
        STORAGE_OK,
        NOW,
        reports(
            solver=report(ComponentName.SOLVER, status=limited),
            trip_planner=report(ComponentName.TRIP_PLANNER, status=down),
        ),
        NOW,
        CITY_OK,
    )

    items = by_name(status)
    assert items[ComponentName.SOLVER] == limited
    assert items[ComponentName.TRIP_PLANNER] == down


def test_storage_down_makes_every_other_component_not_known() -> None:
    storage = ComponentStatus.unavailable(ComponentName.STORAGE, "no database")

    status = system_status_from(storage, NOW, reports(), NOW, CITY_OK)

    items = by_name(status)
    assert items[ComponentName.STORAGE] == storage
    for name in ORDER[1:]:
        assert items[name].state is ComponentState.UNAVAILABLE
        assert items[name].reason == STORAGE_UNKNOWN_REASON
    assert not status.can_simulate.allowed


def test_city_data_is_the_api_s_own_status_and_is_kept_as_given() -> None:
    empty = ComponentStatus.unavailable(ComponentName.CITY_DATA, NO_CITY_DATA_REASON)

    status = system_status_from(STORAGE_OK, NOW, reports(), NOW, empty)

    assert by_name(status)[ComponentName.CITY_DATA] == empty
    assert status.components[-1].name is ComponentName.CITY_DATA


def test_no_city_data_refuses_builds_only_and_says_why() -> None:
    empty = ComponentStatus.unavailable(ComponentName.CITY_DATA, NO_CITY_DATA_REASON)

    status = system_status_from(STORAGE_OK, NOW, reports(), NOW, empty)

    assert NO_CITY_DATA_REASON == "No city data is imported yet"
    assert status.can_build_instances.reasons == (
        BlockingReason(ComponentName.CITY_DATA, NO_CITY_DATA_REASON),
    )
    assert status.can_run_pricing.allowed
    assert status.can_simulate.allowed


def test_city_data_is_not_a_worker_probed_component() -> None:
    assert ComponentName.CITY_DATA not in PROBED_COMPONENTS


def test_a_build_needs_storage_the_runner_the_package_the_city_data_and_the_trip_planner() -> None:
    status = system_status(
        {
            "storage": "No database.",
            "runner": "No runner.",
            "package": "No package.",
            "trip_planner": "No planner.",
            "city_data": "No data.",
        }
    )

    verdict = build_verdict(status, needs_trip_planner=True)

    assert verdict.allowed is False
    assert [item.component for item in verdict.reasons] == [
        ComponentName.STORAGE,
        ComponentName.RUNNER,
        ComponentName.PACKAGE,
        ComponentName.TRIP_PLANNER,
        ComponentName.CITY_DATA,
    ]


def test_a_build_that_keeps_the_routes_does_not_need_the_trip_planner() -> None:
    status = system_status({"trip_planner": "No planner."})

    assert build_verdict(status, needs_trip_planner=False).allowed is True
    assert build_verdict(status, needs_trip_planner=True).reasons == (
        BlockingReason(ComponentName.TRIP_PLANNER, "No planner."),
    )


def test_a_build_never_needs_the_solver() -> None:
    assert build_verdict(system_status({"solver": "No licence."}), True).allowed is True
    assert build_verdict(system_status(limited=("solver",)), True).allowed is True


def test_a_plan_without_a_fingerprint_or_a_manifest_names_the_component_that_lacks_it() -> None:
    verdict = build_verdict(
        system_status(), needs_trip_planner=True, package_missing=True, manifest_missing=True
    )

    assert [(item.component, item.reason) for item in verdict.reasons] == [
        (
            ComponentName.PACKAGE,
            "The runner has not reported the pricing model's package yet: start the worker.",
        ),
        (
            ComponentName.TRIP_PLANNER,
            "The trip planner's graph has no manifest: build it with make otp-graph.",
        ),
    ]


def test_a_component_that_already_blocks_gives_the_only_reason_for_it() -> None:
    verdict = build_verdict(system_status({"package": "No package."}), True, package_missing=True)

    assert verdict.reasons == (BlockingReason(ComponentName.PACKAGE, "No package."),)


def test_a_missing_manifest_does_not_block_a_plan_that_needs_no_trip_planner() -> None:
    assert build_verdict(system_status(), False, manifest_missing=True).allowed is True


def test_the_three_existing_verdicts_are_unchanged_by_the_verdict_for_a_set() -> None:
    status = system_status({"solver": "No licence."})

    assert status.can_run_pricing.reasons == (BlockingReason(ComponentName.SOLVER, "No licence."),)
    assert status.can_build_instances.allowed is True
