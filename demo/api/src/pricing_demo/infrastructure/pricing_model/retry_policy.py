"""The demonstrator's retry policy for the package's trip-planner client (model-notes entry 12).

The package's `OTPClient` retries twice with a growing wait; the demonstrator wants a fixed
number of retries with a fixed wait, on POST too. The policy is mounted at run time, for the
duration of the routes step, on every client the step creates: the package is not edited.
Only `requests` and `urllib3` are imported here; the client class is passed in.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Self

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

POOL_SIZE = 100  # as the package's own adapter
RETRIED_STATUSES = (502, 503, 504)


class FixedWaitRetry(Retry):
    """A `Retry` that waits `wait_s` before every retry, also the first (urllib3 2 does not)."""

    wait_s: float = 0.0

    def get_backoff_time(self) -> float:
        return self.wait_s if self.history else 0.0

    def new(self, **kw: Any) -> Self:
        # `Retry.new` rebuilds the object from the arguments it knows; the wait is carried over.
        copy = super().new(**kw)
        copy.wait_s = self.wait_s
        return copy


def retry_policy(retries: int, wait_s: float) -> Retry:
    policy = FixedWaitRetry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        status_forcelist=RETRIED_STATUSES,
        allowed_methods=frozenset({"POST"}),
        respect_retry_after_header=False,
        backoff_factor=0,
    )
    policy.wait_s = wait_s
    return policy


def retry_adapter(retries: int, wait_s: float) -> HTTPAdapter:
    return HTTPAdapter(
        pool_connections=POOL_SIZE,
        pool_maxsize=POOL_SIZE,
        max_retries=retry_policy(retries, wait_s),
    )


@contextmanager
def mounted_on_otp_clients(client_class: type, retries: int, wait_s: float) -> Iterator[None]:
    """Every client created inside the block gets the policy on `http://` and `https://`; the
    class is restored when the block ends, also on an exception."""
    original: Callable[..., None] = client_class.__post_init__  # type: ignore[attr-defined]

    def patched(self: Any) -> None:
        original(self)
        adapter = retry_adapter(retries, wait_s)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    client_class.__post_init__ = patched  # type: ignore[attr-defined]
    try:
        yield
    finally:
        client_class.__post_init__ = original  # type: ignore[attr-defined]
