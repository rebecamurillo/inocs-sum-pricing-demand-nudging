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
    # What a child process left: the log's excerpt and the peak memory it used (ARCHITECTURE.md
    # § 4.5). Null for an executor that runs no child.
    log_excerpt: str | None = None
    peak_rss_bytes: int | None = None

    @classmethod
    def done(
        cls,
        counts: Mapping[str, Any] | None = None,
        *,
        log_excerpt: str | None = None,
        peak_rss_bytes: int | None = None,
    ) -> Self:
        return cls(
            counts=dict(counts or {}), log_excerpt=log_excerpt, peak_rss_bytes=peak_rss_bytes
        )

    @classmethod
    def failed(
        cls,
        code: str,
        reason: str,
        *,
        log_excerpt: str | None = None,
        peak_rss_bytes: int | None = None,
    ) -> Self:
        return cls(
            failure_code=code,
            failure_reason=reason,
            log_excerpt=log_excerpt,
            peak_rss_bytes=peak_rss_bytes,
        )

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
