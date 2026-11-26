from pricing_demo.application.ports.run_repository import RunRepository
from pricing_demo.domain.runs import RunNotFound


class GetRunLog:
    def __init__(self, repository: RunRepository) -> None:
        self._repository = repository

    def execute(self, run_id: str) -> str:
        """The log excerpts of the run's steps, in step order."""
        run = self._repository.get(run_id)
        if run is None:
            raise RunNotFound(f"No run has the id {run_id}.")
        ordered = sorted(run.steps, key=lambda step: step.position)
        return "\n".join(step.log_excerpt for step in ordered if step.log_excerpt)
