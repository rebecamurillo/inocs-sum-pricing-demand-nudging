import threading
from typing import Protocol


class Waiter(Protocol):
    def wait(self, seconds: float, wake: threading.Event) -> bool:
        """Let `seconds` pass, or less when `wake` is set. True when `wake` was set."""
        ...
