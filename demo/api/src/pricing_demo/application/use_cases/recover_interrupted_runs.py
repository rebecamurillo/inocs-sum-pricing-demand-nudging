from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.domain.run_recovery import is_stale, recover_interrupted
from pricing_demo.domain.runs import Run


class RecoverInterruptedRuns:
    """At a worker's start: queue again, once, the running runs whose heartbeat went stale.

    A run found stale on its second attempt fails with the code `interrupted`.
    """

    def __init__(self, queue: RunQueue, clock: Clock) -> None:
        self._queue = queue
        self._clock = clock

    def execute(self) -> list[Run]:
        now = self._clock.now()
        recovered: list[Run] = []
        for candidate in self._queue.running_runs():
            if not is_stale(candidate, now):
                continue

            def change(run: Run) -> Run:
                # Under the lock: a heartbeat that arrived since the listing wins.
                return recover_interrupted(run, now) if is_stale(run, now) else run

            run = self._queue.update(candidate.id, change)
            if run.state is not candidate.state:
                recovered.append(run)
        return recovered
