from dataclasses import replace
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
    # The solver's constants (`optimizer/solver.py:87-101`), copied like the defaults.
    choice_coefficients={
        "ASC_PT": -0.756,
        "ASC_BIKE": 0.0,
        "ASC_CAR": -0.669,
        "BETA_Cost_BIKE": 0.689,
        "BETA_Time_BIKE": 0.108,
        "BETA_TR_BIKE": 0.199,
        "BETA_Cost_PT": 0.779,
        "BETA_Time_PT": 0.101,
        "BETA_TR_PT": 0.208,
        "BETA_Cost_Car": 0.474,
        "BETA_Cost_park": 0.532,
        "BETA_Time_Car": 0.116,
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
        for index, (seen_at, row) in enumerate(self._rows):
            if row.fingerprint == fingerprint.fingerprint:
                # As PostgreSQL: a row recorded without coefficients gets them once.
                if not row.choice_coefficients and fingerprint.choice_coefficients:
                    self._rows[index] = (
                        seen_at,
                        replace(row, choice_coefficients=fingerprint.choice_coefficients),
                    )
                return
        self._rows.append((at, fingerprint))

    def latest(self) -> PackageFingerprint | None:
        if not self._rows:
            return None
        return max(self._rows, key=lambda row: row[0])[1]

    def get(self, fingerprint: str) -> PackageFingerprint | None:
        return next((row for _, row in self._rows if row.fingerprint == fingerprint), None)

    def clear(self) -> None:
        self._rows.clear()
