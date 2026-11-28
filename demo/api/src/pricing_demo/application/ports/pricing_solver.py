from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pricing_demo.application.ports.step_executor import StopSignal
from pricing_demo.domain.city_instances import Number
from pricing_demo.domain.solves import Solve


@dataclass(frozen=True)
class SolveRequest:
    """What one solve reads. `working_dir` holds the period's `Instance_1.json`; the solver
    writes its output files there."""

    run_id: str
    working_dir: Path
    goals: Mapping[str, Number]  # the seven solver goals (`SOLVER_GOALS`)
    fixed_inputs: Mapping[str, object]  # `FIXED_SOLVER_INPUTS`
    package_fingerprint: str


@dataclass(frozen=True)
class SolveOutcome:
    """How a solve ended: with the solve and the names of the files it wrote into the working
    directory, with a failure code and reason, or stopped."""

    solve: Solve | None = None
    output_files: Sequence[str] = ()
    failure_code: str | None = None
    failure_reason: str | None = None
    log_excerpt: str | None = None
    stopped: bool = False


class PricingSolver(Protocol):
    """The pricing model's solve of one period: the one port that reaches the package's
    optimiser (the real adapter, story 3-4) or its fake."""

    def solve(self, request: SolveRequest, stop: StopSignal) -> SolveOutcome:
        """Solve and return when it ends, or soon after `stop` is set. A failure is an
        outcome with a code of `domain/failure_codes.py`, never an exception."""
        ...
