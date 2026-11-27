from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.characterisation.otp_stub import OtpStub
from tests.characterisation.rig import FIXTURES, City, make_city


@pytest.fixture
def city(tmp_path: Path) -> City:
    return make_city(tmp_path / "data", None, FIXTURES / "gbfs_station_information.json")


@pytest.fixture
def otp_stub() -> Iterator[OtpStub]:
    stub = OtpStub()
    stub.start()
    yield stub
    stub.stop()
