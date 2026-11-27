import signal
import threading
from pathlib import Path

import pytest

from pricing_demo.infrastructure.pricing_model.stage_child import StageChild
from pricing_demo.infrastructure.pricing_model.stage_spec import StageSpec
from tests.unit.infrastructure.pricing_model.test_stage_child import Clock, FakeGroup


def test_a_failing_progress_callback_ends_the_child_before_it_propagates(tmp_path: Path) -> None:
    clock = Clock()
    group = FakeGroup(clock, None, dies_on=(signal.SIGTERM,))

    def fail() -> None:
        raise RuntimeError("the database is gone")

    child = StageChild(lambda spec, folder: group, clock.wait, clock=clock)

    with pytest.raises(RuntimeError, match="the database is gone"):
        child.run(StageSpec("routes", str(tmp_path), 1), threading.Event(), fail)

    assert [sent[0] for sent in group.sent] == [signal.SIGTERM]
    assert group.poll() is not None
