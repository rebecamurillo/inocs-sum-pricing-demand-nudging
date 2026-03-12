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


@dataclass
class OptimizerParams:
    max_displayed_alternatives: int = 10
    mult_A1: int = 1
    capacity: int | None = None
    inventory_level: tuple[float, float] | None = None
    dep_cost: float = 0.0
    cost_bike: float = 0.6
    parking_fee: float = 2.8
    P_bar: float = 0.6
    pt_price: float = 2.0
    theta: float = 0.5
    ridership_weight: float = 8.0
    sol_method: int = -1
    verbose: bool = False
    verbose2: bool = False
