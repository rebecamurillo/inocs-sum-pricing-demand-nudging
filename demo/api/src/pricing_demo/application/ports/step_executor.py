from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, Self

from pricing_demo.domain.runs import Run, RunStep


class StopSignal(Protocol):
    def is_set(self) -> bool:
        """True once the worker asks the executor to stop; a `threading.Event` satisfies it."""
        ...


@dataclass(frozen=True)
class StepOutcome:
    """How a step ended: done with counts, failed with a code and a reason, or stopped."""

    counts: Mapping[str, Any] = field(default_factory=dict)
    failure_code: str | None = None
    failure_reason: str | None = None
    stopped: bool = False

    @classmethod
    def done(cls, counts: Mapping[str, Any] | None = None) -> Self:
        return cls(counts=dict(counts or {}))

    @classmethod
    def failed(cls, code: str, reason: str) -> Self:
        return cls(failure_code=code, failure_reason=reason)

    @classmethod
    def stopped_on_signal(cls) -> Self:
        return cls(stopped=True)


class StepExecutor(Protocol):
    def execute(self, run: Run, step: RunStep, stop: StopSignal) -> StepOutcome:
        """Run the step; return when it ends, or soon after `stop` is set."""
        ...


class StepKeeper(Protocol):
    def keep(self, run: Run, step: RunStep) -> bool:
        """True when the step needs no work: its output already exists and is linked for the
        run's subject. Called before the step starts; the step then ends `kept`."""
        ...
