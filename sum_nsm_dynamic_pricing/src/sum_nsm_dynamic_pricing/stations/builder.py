# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from datetime import datetime
from pathlib import Path

from ..config import PipelineConfig
from ..utils.io import ensure_folder, write_json
from .gbfs import load_gbfs_bike_stations
from .gtfs import load_gtfs_pt_stations
from .providers.base import GBFSProvider


def build_stations(config: PipelineConfig, gbfs_provider: GBFSProvider | None = None) -> Path:
    output_dir = ensure_folder(Path(config.output_dir))

    gbfs_path = config.gbfs_path
    if gbfs_path is None:
        if gbfs_provider is None:
            raise ValueError("Either config.gbfs_path or gbfs_provider must be provided")
        gbfs_path = gbfs_provider.fetch_station_information(output_dir)

    pt_stations = load_gtfs_pt_stations(
        Path(config.gtfs_path),
        config.center_lat,
        config.center_lon,
        config.radius_m,
    )
    bs_stations = load_gbfs_bike_stations(
        Path(gbfs_path),
        config.center_lat,
        config.center_lon,
        config.radius_m,
    )

    stations_payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "center": {"lat": config.center_lat, "lon": config.center_lon},
        "radius_m": config.radius_m,
        "stations": pt_stations + bs_stations,
    }
    target = output_dir / "stations.json"
    write_json(target, stations_payload)
    return target
