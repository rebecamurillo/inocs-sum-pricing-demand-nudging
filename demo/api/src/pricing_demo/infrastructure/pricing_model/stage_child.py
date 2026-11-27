"""The worker's side of a stage child: start it in its own process group, wait for it, end it
on a stop, and read what it left (`stage_runner.py` is the child).

The child is reaped only through `os.wait4` (which also gives its peak memory), never through
`Popen.wait`, so that nothing waits twice.
"""

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, Self

from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.infrastructure.pricing_model.stage_outcome import (
    ExitStatus,
    log_excerpt,
    outcome_of,
    peak_rss_bytes,
)
from pricing_demo.infrastructure.pricing_model.stage_spec import (
    OUTCOME_FILE,
    SPEC_FILE,
    STDERR_FILE,
    STDOUT_FILE,
    StageSpec,
)

GRACE_S = 10.0
TICK_S = 0.2
# How often the worker reads what the child logged while it runs.
PROGRESS_EVERY_S = 0.5


class ProcessGroup(Protocol):
    @property
    def pid(self) -> int: ...

    def poll(self) -> tuple[ExitStatus, int] | None:
        """The child's exit status and `ru_maxrss` once it ended (reaped here), else None."""
        ...

    def signal(self, sig: int) -> None:
        """Send `sig` to the whole group; a group that is already gone raises
        `ProcessLookupError`."""
        ...


class PosixProcessGroup:
    def __init__(self, process: "subprocess.Popen[bytes]") -> None:
        self._process = process
        self._reaped: tuple[ExitStatus, int] | None = None

    @classmethod
    def start(cls, spec_path: Path, working_dir: Path) -> Self:
        with (
            (working_dir / STDOUT_FILE).open("wb") as out,
            (working_dir / STDERR_FILE).open("wb") as err,
        ):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pricing_demo.infrastructure.pricing_model.stage_runner",
                    str(spec_path),
                ],
                cwd=working_dir,
                start_new_session=True,
                stdout=out,
                stderr=err,
            )
        return cls(process)

    @property
    def pid(self) -> int:
        return self._process.pid

    def poll(self) -> tuple[ExitStatus, int] | None:
        if self._reaped is not None:
            return self._reaped
        found, status, usage = os.wait4(self.pid, os.WNOHANG)
        if found == 0:
            return None
        if os.WIFSIGNALED(status):
            exit_status = ExitStatus(signal=os.WTERMSIG(status))
        else:
            exit_status = ExitStatus(code=os.WEXITSTATUS(status))
        # `Popen` never saw the child end: tell it, or it warns when it is collected.
        self._process.returncode = os.waitstatus_to_exitcode(status)
        self._reaped = (exit_status, usage.ru_maxrss)
        return self._reaped

    def signal(self, sig: int) -> None:
        os.killpg(self.pid, sig)


def end_group(
    group: ProcessGroup,
    wait: Callable[[float], None],
    grace_s: float = GRACE_S,
    tick_s: float = TICK_S,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[ExitStatus, int]:
    """SIGTERM to the group, SIGKILL when it is still there after `grace_s`; returns how the
    child ended."""
    _send(group, signal.SIGTERM)
    deadline = clock() + grace_s
    ended = group.poll()
    while ended is None and clock() < deadline:
        wait(tick_s)
        ended = group.poll()
    if ended is None:
        _send(group, signal.SIGKILL)
        while ended is None:
            wait(tick_s)
            ended = group.poll()
    return ended


def _send(group: ProcessGroup, sig: int) -> None:
    try:
        group.signal(sig)
    except ProcessLookupError:
        return


class StageChild:
    """Runs one stage in a child process and maps what it leaves to a `StepOutcome`."""

    def __init__(
        self,
        start: Callable[[Path, Path], ProcessGroup] = PosixProcessGroup.start,
        wait: Callable[[float], None] = time.sleep,
        tick_s: float = TICK_S,
        grace_s: float = GRACE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._start = start
        self._wait = wait
        self._tick_s = tick_s
        self._grace_s = grace_s
        self._clock = clock

    def run(
        self,
        spec: StageSpec,
        stop: StopSignal,
        on_progress: Callable[[], None] | None = None,
    ) -> StepOutcome:
        # Absolute: the child starts in `folder`, where a relative path would not resolve.
        folder = Path(spec.working_dir).absolute()
        spec_path = folder / SPEC_FILE
        spec_path.write_text(spec.to_json(), encoding="utf-8")
        group = self._start(spec_path, folder)
        sent_by_worker = False
        ended = group.poll()
        last_progress = self._clock()
        while ended is None:
            if on_progress is not None and self._clock() - last_progress >= PROGRESS_EVERY_S:
                try:
                    on_progress()
                except BaseException:
                    # The worker cannot follow the step any more: no child is left running.
                    end_group(group, self._wait, self._grace_s, self._tick_s, self._clock)
                    raise
                last_progress = self._clock()
            if stop.is_set():
                sent_by_worker = True
                ended = end_group(group, self._wait, self._grace_s, self._tick_s, self._clock)
                break
            self._wait(self._tick_s)
            ended = group.poll()
        if on_progress is not None:
            on_progress()  # once more: no line the child wrote last is lost
        exit_status, rss = ended
        return outcome_of(
            self._read_outcome(folder),
            exit_status,
            sent_by_worker,
            self._read_log(folder),
            peak_rss_bytes(rss),
        )

    @staticmethod
    def _read_outcome(folder: Path) -> dict[str, Any] | None:
        try:
            data = json.loads((folder / OUTCOME_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _read_log(folder: Path) -> str:
        data = b""
        for name in (STDOUT_FILE, STDERR_FILE):
            try:
                data += (folder / name).read_bytes()
            except OSError:
                continue
        return log_excerpt(data)
