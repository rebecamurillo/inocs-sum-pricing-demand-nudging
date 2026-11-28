"""A step whose key another run stored first, while this run was preparing it: the stored row is
the artefact the step ingests, so its counts and failures are those of the row's run."""

from collections.abc import Mapping
from typing import Any

import pytest

from pricing_demo.application.ports.artifacts import Artifact
from pricing_demo.application.ports.read_model import IngestionBatch
from pricing_demo.domain.city_datasets import CityDataset
from pricing_demo.domain.runs import StepName
from tests.support.builds import FINGERPRINT
from tests.support.runs import T0
from tests.unit.application.test_run_build_step import AREA, Rig, queued


class RecordingIngestion:
    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        self.seen: list[Artifact] = []

    def ingest(
        self, artifact: Artifact, dataset: CityDataset, upstream: Mapping[StepName, Artifact]
    ) -> Mapping[str, Any]:
        self.seen.append(artifact)
        self.rig.builds.read_model.ingest(IngestionBatch(artifact.input_key, artifact.step, {}))
        return {}


def test_the_step_ingests_the_artefact_another_run_stored_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = Rig()
    recording = RecordingIngestion(rig)
    rig.executor = rig.builds.executor(rig.preparation, rig.files, recording)
    run = queued(rig)
    key = rig.planned(AREA).input_key
    assert key is not None
    earlier = Artifact(
        key, AREA, {}, (), "artifacts/area/earlier", FINGERPRINT, T0, "earlier-run", {"rows": 9}
    )
    add = rig.builds.artifacts.add

    def stored_first(artifact: Artifact) -> None:
        add(earlier)
        add(artifact)

    monkeypatch.setattr(rig.builds.artifacts, "add", stored_first)

    outcome = rig.execute(run, AREA)

    assert outcome.failure_code is None
    assert [(item.run_id, item.reported_counts) for item in recording.seen] == [
        ("earlier-run", {"rows": 9})
    ]
