from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.run_queue import RunQueue
from pricing_demo.domain.run_recovery import is_stale, recover_interrupted
from pricing_demo.domain.runs import Run


class RecoverInterruptedRuns:
    """Queue again, once, the running runs whose heartbeat went stale.

    The worker runs it when it starts and every `RECOVERY_EVERY` of its loop. A run found stale
    on its second attempt fails with the code `interrupted`; a stale run with a cancellation
    request is cancelled. `in_hand` is the run this worker is executing: it is never recovered
    by its own worker, whatever its heartbeat says.
    """

    def __init__(self, queue: RunQueue, clock: Clock) -> None:
        self._queue = queue
        self._clock = clock

    def execute(self, in_hand: str | None = None) -> list[Run]:
        now = self._clock.now()
        recovered: list[Run] = []
        for candidate in self._queue.running_runs():
            if candidate.id == in_hand or not is_stale(candidate, now):
                continue

            def change(run: Run) -> Run:
                # Under the lock: a heartbeat that arrived since the listing wins.
                return recover_interrupted(run, now) if is_stale(run, now) else run

            run = self._queue.update(candidate.id, change)
            if run.state is not candidate.state:
                recovered.append(run)
        return recovered
