from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ShowcaseMark:
    pricing_version_id: str
    period_id: str
    marked_at: datetime


class Showcase(Protocol):
    """The one pricing version and period the Home screen shows."""

    def mark(self, pricing_version_id: str, period_id: str, at: datetime) -> None:
        """Make it the showcase, replacing an earlier mark."""
        ...

    def current(self) -> ShowcaseMark | None: ...
