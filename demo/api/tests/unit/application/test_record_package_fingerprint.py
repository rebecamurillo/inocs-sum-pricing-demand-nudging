import logging
from datetime import timedelta

import pytest

from pricing_demo.application.use_cases.record_package_fingerprint import RecordPackageFingerprint
from pricing_demo.domain.package_fingerprint import PackageFingerprint
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.package_fingerprints import (
    FAKE_FINGERPRINT,
    FakePackageFingerprintReader,
    InMemoryPackageFingerprints,
)
from tests.support.runs import T0


class CountingReader:
    def __init__(self) -> None:
        self.reads = 0

    def read(self) -> PackageFingerprint:
        self.reads += 1
        return FAKE_FINGERPRINT


class FailingReader:
    def read(self) -> PackageFingerprint:
        raise OSError("git is not installed")


def test_the_fingerprint_is_recorded_and_returned() -> None:
    store = InMemoryPackageFingerprints()
    record = RecordPackageFingerprint(FakePackageFingerprintReader(), store, FixedClock(T0))

    assert record.execute() == FAKE_FINGERPRINT.fingerprint
    assert store.latest() == FAKE_FINGERPRINT


def test_the_package_is_read_once_and_recorded_again_every_time() -> None:
    reader = CountingReader()
    store = InMemoryPackageFingerprints()
    record = RecordPackageFingerprint(reader, store, FixedClock(T0))
    record.execute()

    store.clear()  # what the e2e reset does
    record.execute()

    assert reader.reads == 1
    assert store.latest() == FAKE_FINGERPRINT


def test_a_failed_read_is_logged_and_nothing_is_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryPackageFingerprints()
    record = RecordPackageFingerprint(FailingReader(), store, FixedClock(T0))

    with caplog.at_level(logging.ERROR):
        assert record.execute() is None

    assert store.latest() is None
    assert "could not be read" in caplog.text


def test_a_failed_read_is_tried_again() -> None:
    class Flaky:
        calls = 0

        def read(self) -> PackageFingerprint:
            self.calls += 1
            if self.calls == 1:
                raise OSError("busy")
            return FAKE_FINGERPRINT

    record = RecordPackageFingerprint(Flaky(), InMemoryPackageFingerprints(), FixedClock(T0))

    assert record.execute() is None
    assert record.execute() == FAKE_FINGERPRINT.fingerprint


def test_the_latest_row_is_the_one_first_seen_last() -> None:
    store = InMemoryPackageFingerprints()
    other = PackageFingerprint("b" * 64, "1", "c", True, {})
    store.record(FAKE_FINGERPRINT, T0)
    store.record(other, T0 + timedelta(seconds=5))
    store.record(FAKE_FINGERPRINT, T0 + timedelta(seconds=9))

    assert store.latest() == other
