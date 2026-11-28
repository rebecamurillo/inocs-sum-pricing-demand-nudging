import os
import time
import uuid


class UuidV7Source:
    """UUIDv7 (RFC 9562): a 48-bit millisecond timestamp, then random bits.

    Python 3.13 has no `uuid.uuid7`, so the layout is built here.
    """

    def __init__(self) -> None:
        self._last_ms = 0

    def new_run_id(self) -> str:
        # If the clock steps back, reuse the last timestamp, so an id from one source never
        # carries an earlier millisecond than the one before it. Within one millisecond the
        # order of the ids is random.
        self._last_ms = max(self._last_ms, time.time_ns() // 1_000_000)
        value = int.from_bytes(os.urandom(10), "big")
        rand_a = (value >> 62) & 0xFFF
        rand_b = value & ((1 << 62) - 1)
        number = (self._last_ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
        return str(uuid.UUID(int=number))
