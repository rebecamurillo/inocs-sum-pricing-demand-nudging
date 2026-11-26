"""The API process never loads the research package: the worker probes it (ARCHITECTURE.md § 16)."""

import subprocess
import sys

import pytest

SCRIPT = """
import json
import sys

from pricing_demo.bootstrap import create_application
from pricing_demo.infrastructure.config.settings import Settings

create_application(Settings(adapters={adapters!r}))
print(json.dumps({{
    "package": "sum_nsm_dynamic_pricing" in sys.modules,
    "adapter": any(
        name.startswith("pricing_demo.infrastructure.pricing_model") for name in sys.modules
    ),
    "gurobipy": "gurobipy" in sys.modules,
}}))
"""


@pytest.mark.parametrize("adapters", ["real", "fake"])
def test_building_the_api_leaves_the_package_and_its_adapter_out_of_the_process(
    adapters: str,
) -> None:
    # A fresh interpreter: this process may already have imported the package.
    result = subprocess.run(
        [sys.executable, "-I", "-c", SCRIPT.format(adapters=adapters)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == '{"package": false, "adapter": false, "gurobipy": false}'
