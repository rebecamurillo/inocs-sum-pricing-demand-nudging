from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class PipelineConfig:
    center_lat: float
    center_lon: float
    radius_m: float
    output_dir: Path
    gtfs_path: Path
    gbfs_path: Optional[Path] = None
    otp_url: str = "http://localhost:8080/otp/gtfs/v1"
    clustering_threshold_m: float = 500.0
    clustering_buffer_m: float = 100.0
    min_od_distance_m: float = 500.0
    seed: Optional[int] = None


@dataclass
class InstanceParams:
    fixed_capacity: int = 20
    min_demand: int = 10
    max_demand: int = 70
    min_inventory_pct: float = 0.0
    max_inventory_pct: float = 1.0
    min_park_time: float = 1.0
    max_park_time: float = 5.0
