from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pricing_demo.application.ports.step_executor import StepOutcome, StopSignal
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.city_instances import InstanceParameters, InstancePeriod
from pricing_demo.domain.runs import StepName

# `(done, total)`: how far the step is.
Progress = Callable[[int, int], None]


@dataclass(frozen=True)
class PreparationRequest:
    run_id: str
    step: StepName
    working_dir: Path
    parameters: InstanceParameters
    dataset: CityDataset
    period: InstancePeriod


class CityPreparation(Protocol):
    """The four steps that prepare a city instance. The model sits behind it."""

    def prepare(
        self, request: PreparationRequest, progress: Progress, stop: StopSignal
    ) -> StepOutcome:
        """Write the step's outputs (`STEP_OUTPUTS`) into `request.working_dir`, which already
        holds the upstream files, and return the counts; or return a failure code and reason,
        or `stopped` once `stop` is set."""
        ...
