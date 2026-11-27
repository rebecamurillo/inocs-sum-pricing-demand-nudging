from pathlib import Path

import pytest

from tests.characterisation.rig import FIXTURES, City, make_city


@pytest.fixture
def city(tmp_path: Path) -> City:
    return make_city(tmp_path / "data", None, FIXTURES / "gbfs_station_information.json")
