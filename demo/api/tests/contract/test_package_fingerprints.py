"""The PackageFingerprints port: one suite, run against the fake and the PostgreSQL adapter."""

from collections.abc import Iterator
from dataclasses import replace

import pytest

from pricing_demo.application.ports.package_fingerprints import PackageFingerprints
from pricing_demo.infrastructure.fakes.package_fingerprints import (
    FAKE_FINGERPRINT,
    InMemoryPackageFingerprints,
)
from tests.support.runs import T0, later


@pytest.fixture(
    params=[
        pytest.param("fake", id="fake"),
        pytest.param("postgres", id="postgres", marks=pytest.mark.integration),
    ]
)
def fingerprints(request: pytest.FixtureRequest) -> Iterator[PackageFingerprints]:
    if request.param == "fake":
        yield InMemoryPackageFingerprints()
    else:
        from pricing_demo.infrastructure.persistence.package_fingerprints import (
            PostgresPackageFingerprints,
        )

        yield PostgresPackageFingerprints(request.getfixturevalue("migrated_database"))


def test_nothing_is_recorded_at_first(fingerprints: PackageFingerprints) -> None:
    assert fingerprints.latest() is None


def test_a_fingerprint_is_read_back_unchanged(fingerprints: PackageFingerprints) -> None:
    fingerprints.record(FAKE_FINGERPRINT, T0)

    assert fingerprints.latest() == FAKE_FINGERPRINT


def test_recording_the_same_fingerprint_again_changes_nothing(
    fingerprints: PackageFingerprints,
) -> None:
    other = replace(FAKE_FINGERPRINT, fingerprint="b" * 64)
    fingerprints.record(FAKE_FINGERPRINT, T0)
    fingerprints.record(other, later(5))

    fingerprints.record(FAKE_FINGERPRINT, later(10))

    assert fingerprints.latest() == other


def test_the_latest_is_the_one_first_seen_last(fingerprints: PackageFingerprints) -> None:
    newer = replace(FAKE_FINGERPRINT, fingerprint="b" * 64, version="2.0.0", git_dirty=True)
    fingerprints.record(newer, later(60))
    fingerprints.record(FAKE_FINGERPRINT, T0)

    assert fingerprints.latest() == newer


def test_the_coefficients_are_read_back(fingerprints: PackageFingerprints) -> None:
    fingerprints.record(FAKE_FINGERPRINT, T0)

    latest = fingerprints.latest()

    assert latest is not None
    assert latest.choice_coefficients == FAKE_FINGERPRINT.choice_coefficients
    assert latest.choice_coefficients["ASC_PT"] == -0.756


def test_a_row_recorded_without_coefficients_gets_them_on_the_next_record(
    fingerprints: PackageFingerprints,
) -> None:
    bare = replace(FAKE_FINGERPRINT, choice_coefficients={})
    fingerprints.record(bare, T0)
    assert fingerprints.latest() == bare

    fingerprints.record(FAKE_FINGERPRINT, later(5))

    assert fingerprints.latest() == FAKE_FINGERPRINT


def test_a_row_with_coefficients_is_not_changed_by_a_later_record(
    fingerprints: PackageFingerprints,
) -> None:
    fingerprints.record(FAKE_FINGERPRINT, T0)
    other = replace(
        FAKE_FINGERPRINT,
        version="9.9.9",
        choice_coefficients={**FAKE_FINGERPRINT.choice_coefficients, "ASC_PT": 1.0},
    )

    fingerprints.record(other, later(5))

    assert fingerprints.latest() == FAKE_FINGERPRINT


def test_a_fingerprint_is_found_by_its_hash(fingerprints: PackageFingerprints) -> None:
    other = replace(FAKE_FINGERPRINT, fingerprint="b" * 64)
    fingerprints.record(FAKE_FINGERPRINT, T0)
    fingerprints.record(other, later(5))

    assert fingerprints.get(FAKE_FINGERPRINT.fingerprint) == FAKE_FINGERPRINT
    assert fingerprints.get("b" * 64) == other
    assert fingerprints.get("c" * 64) is None
