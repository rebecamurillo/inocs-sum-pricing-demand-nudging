"""The fake city's files as the four build steps write them, for the tests of the read model."""

import json
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from pricing_demo.application.ports.city_preparation import PreparationRequest
from pricing_demo.domain.build_plan import STEP_OUTPUTS
from pricing_demo.domain.city_instances import first_period, parameters_from_defaults
from pricing_demo.domain.read_model import RouteFailure
from pricing_demo.domain.runs import StepName
from pricing_demo.infrastructure.fakes.city_datasets import fake_city_dataset
from pricing_demo.infrastructure.fakes.city_preparation import FakeCityPreparation
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.fakes.fake_settings import InMemoryFakeSettings
from pricing_demo.infrastructure.fakes.package_fingerprints import FAKE_FINGERPRINT
from pricing_demo.infrastructure.fakes.waiter import FakeWaiter
from tests.support.runs import T0

DATASET = fake_city_dataset("geneva-2026-11-26", T0)
PERIOD = first_period("geneva-3km.v1", DATASET)
PARAMETERS = parameters_from_defaults(FAKE_FINGERPRINT.defaults, DATASET.preset)


class FakeCity:
    """The files, counts and reported failures of one run of the four steps."""

    def __init__(self, folder: Path, route_failures: Sequence[Mapping[str, str]] = ()) -> None:
        settings = InMemoryFakeSettings()
        settings.set_pricing_model({"route_failures": list(route_failures)})
        port = FakeCityPreparation(settings, FakeWaiter(FixedClock(T0)))
        self.counts: dict[StepName, Mapping[str, Any]] = {}
        self.failures: list[RouteFailure] = []
        for step in STEP_OUTPUTS:
            request = PreparationRequest("run-1", step, folder, PARAMETERS, DATASET, PERIOD)
            outcome = port.prepare(
                request, lambda done, total: None, threading.Event(), self.failures.append
            )
            self.counts[step] = outcome.counts
        self.files: dict[str, Any] = {
            name: json.loads((folder / name).read_text(encoding="utf-8"))
            for names in STEP_OUTPUTS.values()
            for name in names
        }
