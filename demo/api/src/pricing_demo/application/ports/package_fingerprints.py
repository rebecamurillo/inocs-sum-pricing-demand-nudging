from datetime import datetime
from typing import Protocol

from pricing_demo.domain.package_fingerprint import PackageFingerprint


class PackageFingerprintReader(Protocol):
    """The worker's view of the pricing package: what it is and what its defaults are."""

    def read(self) -> PackageFingerprint: ...


class PackageFingerprints(Protocol):
    """The `package_fingerprints` rows."""

    def record(self, fingerprint: PackageFingerprint, at: datetime) -> None:
        """Insert the row when its fingerprint is new; an existing row is left as it is."""
        ...

    def latest(self) -> PackageFingerprint | None:
        """The row first seen last, or None when none was recorded."""
        ...
