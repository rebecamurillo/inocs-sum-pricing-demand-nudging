import pytest
from requests.adapters import HTTPAdapter

from pricing_demo.infrastructure.pricing_model.retry_policy import (
    mounted_on_otp_clients,
    retry_adapter,
    retry_policy,
)


def test_the_policy_retries_connection_read_and_gateway_errors_on_post() -> None:
    policy = retry_policy(3, 2.0)

    assert (policy.total, policy.connect, policy.read, policy.status) == (3, 3, 3, 3)
    assert set(policy.status_forcelist or ()) == {502, 503, 504}
    assert policy.allowed_methods is not None
    assert "POST" in policy.allowed_methods
    assert policy.respect_retry_after_header is False


def test_the_wait_is_the_same_before_every_retry() -> None:
    policy = retry_policy(3, 2.0)
    waits = []
    for _ in range(3):
        policy = policy.increment(method="POST", url="/", error=OSError("x"))
        waits.append(policy.get_backoff_time())

    assert waits == [2.0, 2.0, 2.0]
    assert policy.new().get_backoff_time() == 2.0


def test_the_adapter_carries_the_policy_and_the_pool_sizes() -> None:
    adapter = retry_adapter(2, 0.5)

    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries.total == 2


class Client:
    def __init__(self) -> None:
        self.session = _Session()
        self.__post_init__()

    def __post_init__(self) -> None:
        self.session = _Session()


class _Session:
    def __init__(self) -> None:
        self.mounted: dict[str, object] = {}

    def mount(self, prefix: str, adapter: object) -> None:
        self.mounted[prefix] = adapter


def test_clients_made_inside_the_block_carry_the_adapter_and_the_original_comes_back() -> None:
    original = Client.__post_init__

    with mounted_on_otp_clients(Client, 2, 0.1):
        inside = Client()

    assert set(inside.session.mounted) == {"http://", "https://"}
    assert isinstance(inside.session.mounted["http://"], HTTPAdapter)
    assert Client.__post_init__ is original
    assert Client().session.mounted == {}


def test_the_original_comes_back_after_an_exception() -> None:
    original = Client.__post_init__

    with pytest.raises(RuntimeError), mounted_on_otp_clients(Client, 2, 0.1):
        raise RuntimeError("x")

    assert Client.__post_init__ is original
