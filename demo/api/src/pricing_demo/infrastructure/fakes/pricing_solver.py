"""The fake `PricingSolver`: a deterministic formula of the four goals, written in the model's
output shapes, with no licence behind it (ARCHITECTURE.md § 11.1).

The solve covers the PT + bike options the model offers, at a price; the model offers fewer
options than the flat scheme does (no option from hub H6, and at most `max_displayed_options`
per pair), so the two simulations can differ. What it does besides is read from the
`pricing_model` entry of the fake settings: hold the `pricing_model` step until its run is
released, fail it with a code, and record the licence kind on the solve.
"""

import json
from collections.abc import Mapping
from typing import Any

from pricing_demo.application.ports.pricing_solver import SolveOutcome, SolveRequest
from pricing_demo.application.ports.step_executor import StopSignal
from pricing_demo.application.ports.waiter import Waiter
from pricing_demo.domain.failure_codes import failure_reason
from pricing_demo.domain.runs import StepName
from pricing_demo.domain.solves import (
    Solve,
    SolveOd,
    SolveProvenance,
    SolveQuality,
    SolveRow,
)
from pricing_demo.infrastructure.fakes.component_probe import FakeSettingsSource
from pricing_demo.infrastructure.fakes.hold import hold_until_released
from pricing_demo.infrastructure.pricing_model.solve_reading import package_parameters

SOLUTION_FILE = "solution.json"
# The origin hub the fake model offers nothing from.
UNPRICED_ORIGIN = "H6"
OPTIMAL = 2
TYPES = ("PT+Bike", "PT-Only", "Car")
FAKE_PARAMETERS = {"Threads": 4, "TimeLimit": 7200}
# What a failure's reason is written with when the code names a value (as the fake city's).
FAKE_REASON_VALUES: Mapping[str, object] = {
    "url": "http://trip-planner.fake/otp",
    "d": "2026-03-08",
    "name": "INFEASIBLE",
    "check": "the travellers of a pair do not add up",
    "n": 9,
    "exception_type": "RuntimeError",
    "message": "fake failure",
}


def _arcs(instance: Mapping[str, Any], name: str) -> dict[tuple[str, str], list[Mapping[str, Any]]]:
    found = instance[name]
    arcs = found.items() if isinstance(found, Mapping) else []
    result: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for key, items in arcs:
        origin, _, destination = str(key).partition("_")
        result[(origin, destination)] = list(items)
    return result


def _package_summary(rows: list[SolveRow]) -> dict[str, object]:
    """A record with the keys of the package's `summarize` (`metrics.py:111-135`) that the
    result reads, computed from the rows the way the package does."""
    bike = [row for row in rows if row.type == "PT+Bike"]
    used = [row.bike_price for row in bike if row.flow >= 1 and row.bike_price is not None]
    offered = [row.bike_price for row in bike if row.nu == 1 and row.bike_price is not None]
    flows = {kind: sum(row.flow for row in rows if row.type == kind) for kind in TYPES}
    return {
        "Obj Value": round(sum((row.bike_price or 0.0) * row.flow for row in bike), 2),
        "Total Demand": round(sum(flows.values()), 2),
        "Total Flow (Car)": round(flows["Car"], 2),
        "Total Flow (PT Only)": round(flows["PT-Only"], 2),
        "Total Flow (Multimodal)": round(sum(row.flow for row in bike if row.flow >= 1), 2),
        "Avg Bike Price (Multimodal, Flow ≥ 1)": sum(used) / len(used) if used else None,
        "Avg Bike Price (for all offered arcs)": sum(offered) / len(offered) if offered else None,
    }


class FakePricingSolver:
    """Passes the same contract suite as the real adapter (story 3-4 adds that one)."""

    def __init__(self, settings: FakeSettingsSource, waiter: Waiter) -> None:
        self._settings = settings
        self._waiter = waiter

    def solve(self, request: SolveRequest, stop: StopSignal) -> SolveOutcome:
        if stop.is_set():
            return SolveOutcome(stopped=True)
        held = self._config().get("hold_at") == StepName.PRICING_MODEL.value
        if held and not hold_until_released(self._settings, self._waiter, request.run_id, stop):
            return SolveOutcome(stopped=True)
        # Read after the hold: a scenario sets the failure while the step is held.
        config = self._config()
        failure = config.get("fail_at")
        if isinstance(failure, dict) and failure.get("step") == StepName.PRICING_MODEL.value:
            code = str(failure["code"])
            return SolveOutcome(
                failure_code=code, failure_reason=failure_reason(code, **FAKE_REASON_VALUES)
            )
        instance = json.loads((request.working_dir / "Instance_1.json").read_text(encoding="utf-8"))
        goals = request.goals
        rows, ods = self._rows(instance, goals)
        solve = Solve(
            SolveQuality(
                solver_status=OPTIMAL,
                solver_status_name="OPTIMAL",
                objective_value=sum(
                    (row.bike_price or 0.0) * row.flow for row in rows if row.type == "PT+Bike"
                ),
                gap_pct=0.0,
                solution_time_s=0.0,
                sol_count=1,
                time_limit_reached=False,
            ),
            SolveProvenance(
                gurobi_version="fake",
                licence_kind=str(config.get("licence_kind") or "full"),
                solver_parameters=dict(FAKE_PARAMETERS),
                package_fingerprint=request.package_fingerprint,
                demonstrator_version="fake",
                dependency_lock_sha256="fake",
                platform="fake",
            ),
            tuple(rows),
            tuple(ods),
            _package_summary(rows),
            package_parameters(goals),
        )
        (request.working_dir / SOLUTION_FILE).write_text(
            json.dumps([row.__dict__ for row in rows], sort_keys=True, separators=(",", ":"))
            + "\n",
            encoding="utf-8",
        )
        return SolveOutcome(solve=solve, output_files=(SOLUTION_FILE,))

    def _config(self) -> Mapping[str, Any]:
        config = self._settings.read().get("pricing_model")
        return config if isinstance(config, dict) else {}

    @staticmethod
    def _rows(
        instance: Mapping[str, Any], goals: Mapping[str, float]
    ) -> tuple[list[SolveRow], list[SolveOd]]:
        bike = _arcs(instance, "arcs_pt_bike")
        public = _arcs(instance, "arcs_pt_only")
        car = _arcs(instance, "car_paths")
        shown = int(goals["max_displayed_options"])
        parking = float(goals["car_parking_fee_chf"])
        fare = float(goals["pt_fare_chf"])
        rows: list[SolveRow] = []
        ods: list[SolveOd] = []
        for pair in instance["OD_pairs"]:
            key = (str(pair["origin"]), str(pair["destination"]))
            offered = [
                (rank, arc)
                for rank, arc in enumerate(bike.get(key, []))
                if rank < shown and key[0] != UNPRICED_ORIGIN
            ]
            options = len(offered) + len(public.get(key, [])) + len(car.get(key, []))
            flow = pair["demand"] / options if options else 0.0
            for rank, arc in offered:
                price = round(
                    max(
                        goals["lowest_price_chf"],
                        goals["cost_bike_chf"]
                        + 0.1 * goals["ridership_weight"]
                        + 0.2 * goals["station_balance_weight"]
                        + 0.05 * rank,
                    ),
                    2,
                )
                rows.append(
                    SolveRow(
                        str(arc["arc_id"]),
                        *key,
                        "PT+Bike",
                        1.0,
                        flow,
                        price,
                        price + fare,
                        0.0,
                        0.0,
                    )
                )
            for arc in public.get(key, []):
                rows.append(
                    SolveRow(str(arc["arc_id"]), *key, "PT-Only", 1.0, flow, None, fare, 0.0, 0.0)
                )
            for arc in car.get(key, []):
                cost = float(arc.get("total_travel_cost", 0.0)) + parking
                rows.append(
                    SolveRow(str(arc["arc_id"]), *key, "Car", 1.0, flow, None, cost, 0.0, 0.0)
                )
            ods.append(SolveOd(*key, 0.0))
        rows.sort(key=lambda row: row.arc_id)
        return rows, ods
