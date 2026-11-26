import uuid

from pricing_demo.infrastructure.clock import SystemClock
from pricing_demo.infrastructure.fakes.clock import FixedClock
from pricing_demo.infrastructure.ids import UuidV7Source
from tests.support.runs import T0, later


def test_an_id_is_a_uuid_of_version_7_with_the_rfc_variant() -> None:
    parsed = uuid.UUID(UuidV7Source().new_run_id())

    assert parsed.version == 7
    assert parsed.variant == uuid.RFC_4122


def test_an_id_carries_the_current_time_in_milliseconds() -> None:
    import time

    before = time.time_ns() // 1_000_000
    parsed = uuid.UUID(UuidV7Source().new_run_id())
    after = time.time_ns() // 1_000_000

    assert before <= parsed.int >> 80 <= after


def test_ids_sort_in_creation_order_across_milliseconds() -> None:
    import time

    source = UuidV7Source()
    ids = []
    for _ in range(5):
        ids.append(source.new_run_id())
        time.sleep(0.002)

    assert ids == sorted(ids)
    assert len(set(ids)) == 5


def test_ids_in_one_millisecond_differ() -> None:
    source = UuidV7Source()

    assert len({source.new_run_id() for _ in range(100)}) == 100


def test_the_system_clock_is_timezone_aware_utc() -> None:
    assert SystemClock().now().utcoffset() is not None
    assert SystemClock().now().utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_a_fixed_clock_tells_the_time_it_was_given_until_it_is_set() -> None:
    clock = FixedClock(T0)
    assert clock.now() == T0

    clock.set(later(5))

    assert clock.now() == later(5)
