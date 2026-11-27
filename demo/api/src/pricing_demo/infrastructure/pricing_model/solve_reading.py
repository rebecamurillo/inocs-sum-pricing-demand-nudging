"""From what the package's solve left behind to the `Solve` the demonstrator stores. Pure: no
I/O, no package (the package's names for goals and fields appear here and in the child only).

The package returns neither the solver's status nor its solution count: both are read from its
printed log (model-notes entries 26 and 27).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pricing_demo.domain.failure_codes import (
    SOLVER_NO_SOLUTION,
    SOLVER_SIZE_LIMITED,
    failure_reason,
)
from pricing_demo.domain.pricing_keys import PACKAGE_GOAL_NAMES as PACKAGE_GOAL_NAMES
from pricing_demo.domain.solves import (
    Solve,
    SolveOd,
    SolveProvenance,
    SolveQuality,
    SolveRow,
    SolveRowType,
)

INTEGER_FIELDS = frozenset({"max_displayed_alternatives", "mult_A1"})

# Gurobi's status codes.
STATUS_NAMES: Mapping[int, str] = {
    1: "LOADED",
    2: "OPTIMAL",
    3: "INFEASIBLE",
    4: "INF_OR_UNBD",
    5: "UNBOUNDED",
    6: "CUTOFF",
    7: "ITERATION_LIMIT",
    8: "NODE_LIMIT",
    9: "TIME_LIMIT",
    10: "SOLUTION_LIMIT",
    11: "INTERRUPTED",
    12: "NUMERIC",
    13: "SUBOPTIMAL",
    14: "INPROGRESS",
    15: "USER_OBJ_LIMIT",
    16: "WORK_LIMIT",
    17: "MEM_LIMIT",
}
UNKNOWN_STATUS = 0
UNKNOWN_STATUS_NAME = "UNKNOWN"
TIME_LIMIT = 9
NO_SOLUTION_STATUSES = frozenset({3, 4})

_ERROR_LINE = re.compile(r"^Gurobi error during optimization:(.*)$", re.MULTILINE)
_STATUS = re.compile(r"Solver ended(?: .*?)? with status (\d+)")
_SOL_COUNT = re.compile(r"Total feasible solutions found: (\d+)")
_PARAMETER = re.compile(r"^Set parameter (\S+) to value (.*)$", re.MULTILINE)
SIZE_LIMIT_CODE = "10010"
SIZE_LIMIT_TEXT = "size-limited licen"
RESTRICTED_BANNER = "Restricted license"
RESULTS_FILE = "optimization_instance_results.json"


def optimizer_fields(goals: Mapping[str, Any], fixed_inputs: Mapping[str, Any]) -> dict[str, Any]:
    """The keyword arguments of the package's `OptimizerParams` for a solve."""
    fields: dict[str, Any] = {
        PACKAGE_GOAL_NAMES[name]: value
        for name, value in goals.items()
        if name in PACKAGE_GOAL_NAMES
    }
    fields.update(fixed_inputs)
    for name in INTEGER_FIELDS & fields.keys():
        fields[name] = int(fields[name])
    return fields


def package_parameters(goals: Mapping[str, Any]) -> dict[str, Any]:
    """The goals a solve ran with under the package's names (the goal subset of
    `optimizer_fields`)."""
    fields = optimizer_fields(goals, {})
    return {name: fields[name] for name in PACKAGE_GOAL_NAMES.values() if name in fields}


def size_limited(stdout: str) -> bool:
    """The package prints `Gurobi error during optimization: {message}` and goes on; the
    message of the size-limit error names the licence and carries no code."""
    for match in _ERROR_LINE.finditer(stdout):
        line = match.group(1)
        if SIZE_LIMIT_CODE in line or SIZE_LIMIT_TEXT in line.lower():
            return True
    return False


def solver_status(stdout: str) -> int | None:
    found = _STATUS.findall(stdout)
    return int(found[-1]) if found else None


def sol_count(stdout: str) -> int:
    found = _SOL_COUNT.findall(stdout)
    return int(found[-1]) if found else 0


def _typed(text: str) -> object:
    for kind in (int, float):
        try:
            return kind(text)
        except ValueError:
            continue
    return text


def solver_parameters(stdout: str) -> dict[str, object]:
    """Every parameter the solver reported setting; the last report of a name wins."""
    return {name: _typed(value.strip()) for name, value in _PARAMETER.findall(stdout)}


def licence_kind(stdout: str) -> str:
    return "limited" if RESTRICTED_BANNER in stdout else "full"


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def rows_from(instances: Sequence[Mapping[str, Any]]) -> tuple[list[SolveRow], list[SolveOd]]:
    """The package's `instances` list: an item with `Instance OD` is a hub pair's gamma, any
    other item an option. Rows by arc id, pairs by origin and destination."""
    rows: list[SolveRow] = []
    ods: list[SolveOd] = []
    for item in instances:
        origin, _, destination = str(item["OD"]).partition("->")
        if "Instance OD" in item:
            ods.append(SolveOd(origin, destination, float(item["gamma"])))
            continue
        rows.append(
            SolveRow(
                arc_id=str(item["Arc ID"]),
                origin_hub=origin,
                destination_hub=destination,
                type=_row_type(item["Type"]),
                nu=float(item["nu"]),
                flow=float(item["Flow (q)"]),
                bike_price=_number(item.get("Bike Price")),
                total_price=_number(item.get("Total Price")),
                z_value=_number(item.get("z value")),
                relaxation_difference=_number(item.get("Relaxation Difference")),
            )
        )
    rows.sort(key=lambda row: row.arc_id)
    ods.sort(key=lambda od: (od.origin_hub, od.destination_hub))
    return rows, ods


def _row_type(value: object) -> SolveRowType:
    if value == "PT+Bike" or value == "PT-Only" or value == "Car":
        return value
    raise ValueError(f"{value!r} is not a type of option the package writes")


@dataclass(frozen=True)
class ProvenanceBase:
    """What a solve's provenance holds besides what the child and its log tell."""

    package_fingerprint: str
    demonstrator_version: str
    dependency_lock_sha256: str


def read_solve(
    results: object,
    stdout: str,
    facts: Mapping[str, Any],
    base: ProvenanceBase,
) -> Solve | tuple[str, str]:
    """The solve, or the failure `(code, reason)` of a solve that left no result. `results` is
    the parsed `optimization_instance_results.json` (`None` when the package found nothing)."""
    if size_limited(stdout):
        return SOLVER_SIZE_LIMITED, failure_reason(SOLVER_SIZE_LIMITED)
    status = solver_status(stdout)
    number = status if status is not None else UNKNOWN_STATUS
    name = STATUS_NAMES.get(number, UNKNOWN_STATUS_NAME)
    count = sol_count(stdout)
    # A result without `instances` is the package's partial recovery of metrics.
    if (
        not isinstance(results, dict)
        or not isinstance(results.get("instances"), list)
        or number in NO_SOLUTION_STATUSES
        or (number == TIME_LIMIT and count == 0)
    ):
        return SOLVER_NO_SOLUTION, failure_reason(SOLVER_NO_SOLUTION, name=name)
    rows, ods = rows_from(results["instances"])
    return Solve(
        SolveQuality(
            solver_status=number,
            solver_status_name=name,
            objective_value=_number(results.get("Objective Value")),
            gap_pct=_number(results.get("Gap (%)")),
            solution_time_s=_number(results.get("Solution Time (s)")),
            sol_count=count,
            time_limit_reached=number == TIME_LIMIT,
        ),
        SolveProvenance(
            gurobi_version=str(facts.get("gurobi_version", "")),
            licence_kind=licence_kind(stdout),
            solver_parameters=solver_parameters(stdout),
            package_fingerprint=base.package_fingerprint,
            demonstrator_version=base.demonstrator_version,
            dependency_lock_sha256=base.dependency_lock_sha256,
            platform=str(facts.get("platform", "")),
        ),
        tuple(rows),
        tuple(ods),
    )
