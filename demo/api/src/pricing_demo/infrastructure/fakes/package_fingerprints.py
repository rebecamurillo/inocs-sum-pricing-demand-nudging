from datetime import datetime

from pricing_demo.domain.package_fingerprint import PackageFingerprint

# The defaults of the package's dataclasses (`sum_nsm_dynamic_pricing/src/.../config.py`),
# copied: the fake adapter set never imports the package. A path or None is stored as it
# serialises in the real adapter's JSON.
FAKE_FINGERPRINT = PackageFingerprint(
    fingerprint="f" * 64,
    version="0.0.0-fake",
    git_commit="0" * 40,
    git_dirty=False,
    defaults={
        "PipelineConfig": {
            "gbfs_path": None,
            "otp_url": "http://localhost:8080/otp/gtfs/v1",
            "clustering_threshold_m": 500.0,
            "clustering_buffer_m": 100.0,
            "min_od_distance_m": 500.0,
            "seed": None,
            "otp_workers": 4,
            "otp_request_delay_s": 0.05,
            "otp_timestamp": "2026-03-08T08:30:00.000000Z",
        },
        "InstanceParams": {
            "fixed_capacity": 20,
            "min_demand": 10,
            "max_demand": 70,
            "min_inventory_pct": 0.0,
            "max_inventory_pct": 1.0,
            "min_park_time": 1.0,
            "max_park_time": 5.0,
        },
        "OptimizerParams": {
            "max_displayed_alternatives": 10,
            "mult_A1": 1,
            "capacity": None,
            "inventory_level": None,
            "dep_cost": 0.0,
            "cost_bike": 0.6,
            "parking_fee": 2.8,
            "P_bar": 0.6,
            "pt_price": 2.0,
            "theta": 0.5,
            "ridership_weight": 8.0,
            "sol_method": -1,
            "verbose": False,
            "verbose2": False,
        },
    },
)


class FakePackageFingerprintReader:
    def read(self) -> PackageFingerprint:
        return FAKE_FINGERPRINT


class InMemoryPackageFingerprints:
    """The recorded fingerprints in a list; passes the same contract suite as PostgreSQL."""

    def __init__(self) -> None:
        self._rows: list[tuple[datetime, PackageFingerprint]] = []

    def record(self, fingerprint: PackageFingerprint, at: datetime) -> None:
        if all(row.fingerprint != fingerprint.fingerprint for _, row in self._rows):
            self._rows.append((at, fingerprint))

    def latest(self) -> PackageFingerprint | None:
        if not self._rows:
            return None
        return max(self._rows, key=lambda row: row[0])[1]

    def clear(self) -> None:
        self._rows.clear()
