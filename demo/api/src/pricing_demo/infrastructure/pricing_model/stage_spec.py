"""The spec file the worker hands to the stage child (`stage_runner`), and the names of the
files the child leaves in its working directory.

Plain standard library: the worker and the child both read it, the package is not involved.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

SPEC_FILE = "stage-spec.json"
OUTCOME_FILE = "outcome.json"
PROGRESS_FILE = "progress.jsonl"
STDOUT_FILE = "stdout.log"
STDERR_FILE = "stderr.log"
# What the pricing-model child learned that the solver's output does not say.
SOLVE_FACTS_FILE = "solve_facts.json"
# The first record of the package's own summary of the solution (`optimizer.summarize`).
PACKAGE_SUMMARY_FILE = "package_summary.json"

StageStep = Literal["area", "hubs", "routes", "travellers_and_bikes", "pricing_model"]
STAGE_STEPS: tuple[StageStep, ...] = (
    "area",
    "hubs",
    "routes",
    "travellers_and_bikes",
    "pricing_model",
)


@dataclass(frozen=True)
class StageSpec:
    """What one child runs: the step, where, who started it, and the package's own settings
    (`PipelineConfig` fields in `pipeline`, `InstanceParams` fields in `instance`)."""

    step: StageStep
    working_dir: str
    parent_pid: int
    pipeline: Mapping[str, Any] = field(default_factory=dict)
    instance: Mapping[str, Any] = field(default_factory=dict)
    # The routes step's own settings: `retries`, `retry_wait_s` and `routing_date`.
    routes: Mapping[str, Any] = field(default_factory=dict)
    # The pricing-model step's `OptimizerParams` fields.
    optimizer: Mapping[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "step": self.step,
                "working_dir": self.working_dir,
                "parent_pid": self.parent_pid,
                "pipeline": dict(self.pipeline),
                "instance": dict(self.instance),
                "routes": dict(self.routes),
                "optimizer": dict(self.optimizer),
            },
            sort_keys=True,
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "StageSpec":
        data = json.loads(text)
        step = data["step"]
        if step not in STAGE_STEPS:
            raise ValueError(f"{step!r} is not a step the stage child runs")
        return cls(
            step,
            str(data["working_dir"]),
            int(data["parent_pid"]),
            dict(data.get("pipeline", {})),
            dict(data.get("instance", {})),
            dict(data.get("routes", {})),
            dict(data.get("optimizer", {})),
        )
