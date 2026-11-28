import threading


class SystemWaiter:
    def wait(self, seconds: float, wake: threading.Event) -> bool:
        return wake.wait(seconds)
