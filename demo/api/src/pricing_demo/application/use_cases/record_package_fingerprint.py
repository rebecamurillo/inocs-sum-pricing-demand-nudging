import logging

from pricing_demo.application.ports.clock import Clock
from pricing_demo.application.ports.package_fingerprints import (
    PackageFingerprintReader,
    PackageFingerprints,
)
from pricing_demo.domain.package_fingerprint import PackageFingerprint

logger = logging.getLogger(__name__)


class RecordPackageFingerprint:
    """Reads the package once and records it on every call (insert if new), so a row that the
    e2e reset deleted comes back with the next heartbeat. A read that fails is logged and the
    worker goes on: the `package` component already reports why."""

    def __init__(
        self, reader: PackageFingerprintReader, store: PackageFingerprints, clock: Clock
    ) -> None:
        self._reader = reader
        self._store = store
        self._clock = clock
        self._read: PackageFingerprint | None = None

    def current(self) -> str | None:
        """The fingerprint read so far, without reading or recording anything."""
        return self._read.fingerprint if self._read is not None else None

    def execute(self) -> str | None:
        """The recorded fingerprint, or None when the package could not be read."""
        if self._read is None:
            try:
                self._read = self._reader.read()
            except Exception:
                logger.exception("The package fingerprint could not be read")
                return None
        self._store.record(self._read, self._clock.now())
        return self._read.fingerprint
