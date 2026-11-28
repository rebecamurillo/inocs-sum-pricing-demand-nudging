import pytest

from pricing_demo.domain.system_status import ComponentName, ComponentStatus
from pricing_demo.infrastructure.config.settings import DEMO_DIR, Settings
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.pricing_model.package_fingerprint import (
    PackageFingerprintReader,
)
from pricing_demo.infrastructure.pricing_model.package_probe import PackageProbe
from pricing_demo.infrastructure.pricing_model.solver_probe import SolverProbe
from pricing_demo.infrastructure.trip_planner.otp_probe import OtpProbe

pytestmark = pytest.mark.live


def test_the_package_probe_answers() -> None:
    status = PackageProbe().check()

    assert status == ComponentStatus.ready(ComponentName.PACKAGE), status.reason


def test_the_solver_probe_answers() -> None:
    status = SolverProbe().check()

    assert status == ComponentStatus.ready(ComponentName.SOLVER), status.reason


def test_the_trip_planner_probe_answers() -> None:
    status = OtpProbe(Settings().otp_url).check()

    assert status == ComponentStatus.ready(ComponentName.TRIP_PLANNER), status.reason


def test_the_fake_fingerprint_holds_the_defaults_of_the_real_package() -> None:
    real = PackageFingerprintReader(DEMO_DIR.parent / "sum_nsm_dynamic_pricing").read()

    assert real.defaults == FAKE_FINGERPRINT.defaults
    assert real.choice_coefficients == FAKE_FINGERPRINT.choice_coefficients
