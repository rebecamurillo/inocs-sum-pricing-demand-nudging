from typing import Protocol


class IdSource(Protocol):
    def new_run_id(self) -> str:
        """A new run identifier: a UUIDv7 in its text form."""
        ...
