from pricing_demo.application.step_durations import StepDurations
from pricing_demo.domain.pricing_versions import new_draft_goals
from pricing_demo.domain.runs import RunKind, RunState, StepName, StepState
from tests.support.builds import MemoryBuilds
from tests.support.pricing_versions import built_in_memory
from tests.support.runs import T0, later, make_run, step


def _rig_with_a_finished_model_step(seconds: float) -> tuple[MemoryBuilds, str]:
    rig = MemoryBuilds()
    instance_version = built_in_memory(rig)
    rig.pricing.read_durations_from(rig.instances)
    version = rig.pricing.create_draft(
        instance_version.id, None, new_draft_goals(None), f"{instance_version.id}.mon-08", None, T0
    )
    rig.runs.add(
        make_run(
            "done-1",
            kind=RunKind.PRICING,
            subject_id=version.id,
            state=RunState.SUCCEEDED,
            queued_at=later(10),
            steps=(
                step(
                    1,
                    StepName.PRICING_MODEL,
                    StepState.DONE,
                    started_at=later(10),
                    finished_at=later(10 + seconds),
                ),
            ),
        )
    )
    return rig, version.id


def test_a_pricing_run_reads_the_last_pricing_model_duration_of_its_instance() -> None:
    rig, version_id = _rig_with_a_finished_model_step(75)
    queued = make_run("next", kind=RunKind.PRICING, subject_id=version_id, queued_at=later(500))

    durations = StepDurations(rig.pricing, rig.instances).of(queued)

    assert durations == {StepName.PRICING_MODEL: 75}


def test_a_pricing_run_with_no_earlier_step_on_the_instance_has_no_duration() -> None:
    rig = MemoryBuilds()
    instance_version = built_in_memory(rig)
    rig.pricing.read_durations_from(rig.instances)
    version = rig.pricing.create_draft(
        instance_version.id, None, new_draft_goals(None), f"{instance_version.id}.mon-08", None, T0
    )
    queued = make_run("next", kind=RunKind.PRICING, subject_id=version.id)

    assert StepDurations(rig.pricing, rig.instances).of(queued) == {}


def test_a_build_run_has_no_durations() -> None:
    rig, _ = _rig_with_a_finished_model_step(75)

    assert StepDurations(rig.pricing, rig.instances).of(make_run("build-2")) == {}
