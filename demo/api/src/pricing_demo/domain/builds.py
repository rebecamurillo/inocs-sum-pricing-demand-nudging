"""The refusals of a request to build a version."""

from collections.abc import Sequence

from pricing_demo.domain.errors import DomainError
from pricing_demo.domain.instance_rules import RuleResult
from pricing_demo.domain.system_status import BlockingReason


class RuleBroken(DomainError):
    def __init__(self, failures: Sequence[RuleResult]) -> None:
        self.failures = tuple(failures)
        super().__init__(f"{len(self.failures)} rule(s) of the draft are broken.")


class RunActive(DomainError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"The run {run_id} of this version is queued or running.")


class AlreadyBuilt(DomainError):
    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The version {version_id} is already built.")


class ComponentUnavailable(DomainError):
    def __init__(self, reasons: Sequence[BlockingReason]) -> None:
        self.reasons = tuple(reasons)
        listed = "; ".join(f"{item.component}: {item.reason}" for item in self.reasons)
        super().__init__(f"The build needs components that are not available. {listed}")


class DraftChanged(DomainError):
    """The draft's values changed between the rule check and the seal (a concurrent edit): the
    values checked are not the ones that would be sealed, so nothing is sealed or queued."""

    def __init__(self, version_id: str) -> None:
        self.version_id = version_id
        super().__init__(f"The draft {version_id} changed while its build was being queued.")
