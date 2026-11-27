import json
import signal
import threading
from pathlib import Path

import pytest

from pricing_demo.application.ports.step_executor import StepOutcome
from pricing_demo.infrastructure.pricing_model.stage_child import StageChild, end_group
from pricing_demo.infrastructure.pricing_model.stage_outcome import ExitStatus
from pricing_demo.infrastructure.pricing_model.stage_spec import (
    OUTCOME_FILE,
    SPEC_FILE,
    STDERR_FILE,
    STDOUT_FILE,
    StageSpec,
)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def wait(self, seconds: float) -> None:
        self.now += seconds


class FakeGroup:
    """Ends after `ends_after` seconds of the fake clock, or on the first of `dies_on`."""

    pid = 1234

    def __init__(
        self, clock: Clock, ends_after: float | None, dies_on: tuple[int, ...] = ()
    ) -> None:
        self.clock = clock
        self.ends_after = ends_after
        self.dies_on = dies_on
        self.sent: list[tuple[int, float]] = []
        self.died: ExitStatus | None = None

    def poll(self) -> tuple[ExitStatus, int] | None:
        if self.died is not None:
            return self.died, 2048
        if self.ends_after is not None and self.clock.now >= self.ends_after:
            return ExitStatus(code=0), 2048
        return None

    def signal(self, sig: int) -> None:
        self.sent.append((sig, self.clock.now))
        if sig in self.dies_on:
            self.died = ExitStatus(signal=sig)


def test_sigterm_ends_a_group_that_leaves_and_no_sigkill_follows() -> None:
    clock = Clock()
    group = FakeGroup(clock, None, dies_on=(signal.SIGTERM,))

    status, _ = end_group(group, clock.wait, clock=clock)

    assert [item[0] for item in group.sent] == [signal.SIGTERM]
    assert status == ExitStatus(signal=signal.SIGTERM)


def test_sigkill_follows_after_ten_seconds_when_the_group_is_still_there() -> None:
    clock = Clock()
    group = FakeGroup(clock, None, dies_on=(signal.SIGKILL,))

    end_group(group, clock.wait, clock=clock)

    assert [item[0] for item in group.sent] == [signal.SIGTERM, signal.SIGKILL]
    assert group.sent[1][1] >= 10.0
    assert group.sent[1][1] < 10.5


def test_a_group_already_gone_is_not_an_error() -> None:
    clock = Clock()

    class Gone(FakeGroup):
        def signal(self, sig: int) -> None:
            raise ProcessLookupError

    group = Gone(clock, 0.0)

    status, _ = end_group(group, clock.wait, clock=clock)

    assert status == ExitStatus(code=0)


def run(tmp_path: Path, group: FakeGroup, clock: Clock, stop_after: float | None) -> StepOutcome:
    class Stop:
        def is_set(self) -> bool:
            return stop_after is not None and clock.now >= stop_after

    def start(spec_path: Path, folder: Path) -> FakeGroup:
        (folder / STDOUT_FILE).write_text("out\n", encoding="utf-8")
        (folder / STDERR_FILE).write_text("err\n", encoding="utf-8")
        return group

    child = StageChild(start, clock.wait, clock=clock)
    spec = StageSpec("area", str(tmp_path), 1)
    return child.run(spec, Stop())


def test_a_group_that_ends_by_itself_gets_no_signal_and_its_files_are_read(
    tmp_path: Path,
) -> None:
    clock = Clock()
    group = FakeGroup(clock, 1.0)
    (tmp_path / OUTCOME_FILE).write_text(json.dumps({"status": "done", "counts": {"n": 2}}))

    outcome = run(tmp_path, group, clock, None)

    assert group.sent == []
    assert (tmp_path / SPEC_FILE).is_file()
    assert dict(outcome.counts) == {"n": 2}
    assert outcome.log_excerpt == "out\nerr\n"
    assert outcome.peak_rss_bytes == 2048 * 1024


def test_a_stop_sends_sigterm_and_the_outcome_is_stopped(tmp_path: Path) -> None:
    clock = Clock()
    group = FakeGroup(clock, None, dies_on=(signal.SIGTERM,))

    outcome = run(tmp_path, group, clock, 0.5)

    assert [item[0] for item in group.sent] == [signal.SIGTERM]
    assert outcome.stopped is True


def test_a_signal_nobody_sent_ends_killed(tmp_path: Path) -> None:
    clock = Clock()
    group = FakeGroup(clock, None)
    group.died = ExitStatus(signal=signal.SIGKILL)

    outcome = run(tmp_path, group, clock, None)

    assert outcome.failure_code == "killed"


def test_a_relative_working_directory_is_made_absolute_before_the_child_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "w").mkdir()
    clock = Clock()
    started: list[tuple[Path, Path]] = []

    def start(spec_path: Path, folder: Path) -> FakeGroup:
        started.append((spec_path, folder))
        return FakeGroup(clock, 0.0)

    StageChild(start, clock.wait, clock=clock).run(StageSpec("area", "w", 1), threading.Event())

    assert started == [(tmp_path / "w" / SPEC_FILE, tmp_path / "w")]
