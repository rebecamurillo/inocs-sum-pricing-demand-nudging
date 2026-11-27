import signal
import sys

import pytest

from pricing_demo.infrastructure.pricing_model.stage_outcome import (
    ExitStatus,
    log_excerpt,
    outcome_of,
    peak_rss_bytes,
)

DONE = ExitStatus(code=0)
FAILED = ExitStatus(code=1)


def error(kind: str, message: str) -> dict[str, object]:
    return {
        "status": "error",
        "exception_type": kind,
        "message": message,
        "traceback": "Traceback (most recent call last):\n  File secret.py",
    }


def test_the_packages_unbalanced_instance_error_is_instance_unbalanced() -> None:
    text = "Second instance validation failed, there are still unbalanced arcs despite fix"

    outcome = outcome_of(error("ValueError", text), FAILED, False, "log", 5)

    assert outcome.failure_code == "instance_unbalanced"
    assert outcome.failure_reason == (
        "the instance still has unbalanced bike options after the package's fix"
    )


@pytest.mark.parametrize(("kind", "message"), [("ValueError", "other"), ("RuntimeError", "boom")])
def test_any_other_exception_is_a_stage_error_without_its_traceback(
    kind: str, message: str
) -> None:
    outcome = outcome_of(error(kind, message), FAILED, False, "log", 5)

    assert outcome.failure_code == "stage_error"
    assert outcome.failure_reason == f"{kind}: {message}"
    assert "Traceback" not in (outcome.failure_reason or "")


def test_a_signal_the_worker_did_not_send_is_killed() -> None:
    outcome = outcome_of(None, ExitStatus(signal=signal.SIGKILL), False, "log", 5)

    assert outcome.failure_code == "killed"
    assert outcome.failure_reason == (
        "the process was stopped by the system (signal 9); the machine may be out of memory"
    )


def test_a_signal_the_worker_sent_is_a_stop() -> None:
    outcome = outcome_of(None, ExitStatus(signal=signal.SIGTERM), True, "log", 5)

    assert outcome.stopped is True
    assert outcome.failure_code is None


def test_no_outcome_file_with_a_failing_exit_code_is_a_stage_error() -> None:
    outcome = outcome_of(None, FAILED, False, "log", 5)

    assert outcome.failure_code == "stage_error"
    assert outcome.failure_reason == "the stage child exited with code 1 without an outcome"


def test_done_carries_the_counts_the_log_and_the_peak_memory() -> None:
    outcome = outcome_of({"status": "done", "counts": {"a": 1}}, DONE, False, "log", 77)

    assert outcome.failure_code is None
    assert dict(outcome.counts) == {"a": 1}
    assert (outcome.log_excerpt, outcome.peak_rss_bytes) == ("log", 77)


def test_a_failure_carries_the_log_and_the_peak_memory() -> None:
    outcome = outcome_of(error("RuntimeError", "x"), FAILED, False, "log", 77)

    assert (outcome.log_excerpt, outcome.peak_rss_bytes) == ("log", 77)


def test_a_log_up_to_twice_the_limit_is_kept_whole() -> None:
    data = b"a" * 8 + b"b" * 8

    assert log_excerpt(data, limit=8) == data.decode()


def test_a_longer_log_keeps_its_first_and_last_limit_bytes_around_a_marker() -> None:
    data = b"a" * 8 + b"m" * 5 + b"z" * 8

    assert log_excerpt(data, limit=8) == "aaaaaaaa\n… 5 bytes omitted …\nzzzzzzzz"


def test_the_default_limit_is_128_kib() -> None:
    data = b"x" * (256 * 1024 + 1)

    excerpt = log_excerpt(data)

    assert "1 bytes omitted" in excerpt
    assert len(excerpt) < 256 * 1024 + 40


def test_a_log_is_decoded_with_replacement() -> None:
    assert log_excerpt(b"\xff") == "�"


def test_peak_memory_is_in_bytes_whatever_the_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    assert peak_rss_bytes(10) == 10240
    monkeypatch.setattr(sys, "platform", "darwin")
    assert peak_rss_bytes(10) == 10
