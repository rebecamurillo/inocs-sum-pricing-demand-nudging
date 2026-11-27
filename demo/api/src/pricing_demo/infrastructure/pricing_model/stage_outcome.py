"""From what a stage child left behind to the step's outcome. Pure: no I/O, no package.

The reasons are the texts of ARCHITECTURE.md § 4.7, through `failure_reason`; a traceback is
only ever in the stored log.
"""

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.domain.failure_codes import INSTANCE_UNBALANCED, KILLED, failure_reason
from pricing_demo.domain.run_recovery import STAGE_ERROR

LOG_LIMIT = 128 * 1024
# The text the package raises at `pipeline.py:63-66`.
UNBALANCED_MESSAGE_START = "Second instance validation failed"


@dataclass(frozen=True)
class ExitStatus:
    """How the child ended: by an exit code, or by a signal."""

    code: int | None = None
    signal: int | None = None


def log_excerpt(data: bytes, limit: int = LOG_LIMIT) -> str:
    """The whole log when it is at most `2 * limit` bytes, else its first and last `limit`
    bytes around a line that says how many were left out."""
    if len(data) <= 2 * limit:
        return data.decode("utf-8", errors="replace")
    omitted = len(data) - 2 * limit
    head = data[:limit].decode("utf-8", errors="replace")
    tail = data[-limit:].decode("utf-8", errors="replace")
    return f"{head}\n… {omitted} bytes omitted …\n{tail}"


def peak_rss_bytes(ru_maxrss: int) -> int:
    """`ru_maxrss` is in kibibytes on Linux and in bytes on macOS."""
    return ru_maxrss if sys.platform == "darwin" else ru_maxrss * 1024


def outcome_of(
    outcome: Mapping[str, Any] | None,
    exit_status: ExitStatus,
    sent_by_worker: bool,
    log: str,
    peak_rss: int,
) -> StepOutcome:
    if exit_status.signal is not None:
        if sent_by_worker:
            return StepOutcome(stopped=True, log_excerpt=log, peak_rss_bytes=peak_rss)
        return StepOutcome(
            failure_code=KILLED,
            failure_reason=failure_reason(KILLED, n=exit_status.signal),
            log_excerpt=log,
            peak_rss_bytes=peak_rss,
        )
    if outcome is None:
        return _failed(
            STAGE_ERROR,
            f"the stage child exited with code {exit_status.code} without an outcome",
            log,
            peak_rss,
        )
    if outcome.get("status") == "done":
        return StepOutcome(
            counts=dict(outcome.get("counts") or {}), log_excerpt=log, peak_rss_bytes=peak_rss
        )
    kind, message = str(outcome.get("exception_type", "Exception")), str(outcome.get("message", ""))
    if kind == "ValueError" and message.startswith(UNBALANCED_MESSAGE_START):
        return _failed(INSTANCE_UNBALANCED, failure_reason(INSTANCE_UNBALANCED), log, peak_rss)
    return _failed(
        STAGE_ERROR,
        failure_reason(STAGE_ERROR, exception_type=kind, message=message),
        log,
        peak_rss,
    )


def _failed(code: str, reason: str, log: str, peak_rss: int) -> StepOutcome:
    return StepOutcome(
        failure_code=code, failure_reason=reason, log_excerpt=log, peak_rss_bytes=peak_rss
    )
