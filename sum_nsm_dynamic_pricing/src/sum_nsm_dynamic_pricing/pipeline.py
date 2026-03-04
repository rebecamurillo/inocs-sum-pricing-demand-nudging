from pathlib import Path

from .clustering.hub_builder import build_hubs
from .config import InstanceParams, PipelineConfig
from .instance.generator import generate_instance
from .routing.route_builder import build_od_routes
from .stations.builder import build_stations
from .stations.providers.base import GBFSProvider


class InstancePipeline:
    def __init__(self, config: PipelineConfig, gbfs_provider: GBFSProvider | None = None):
        self.config = config
        self.gbfs_provider = gbfs_provider

    def prepare_stations(self) -> Path:
        return build_stations(self.config, self.gbfs_provider)

    def build_hubs(self, stations_path: Path | None = None) -> Path:
        stations_file = stations_path or Path(self.config.output_dir) / "stations.json"
        hubs_path, _, _ = build_hubs(stations_file, self.config)
        return hubs_path

    def compute_routes(self, hubs_path: Path | None = None) -> Path:
        hub_file = hubs_path or Path(self.config.output_dir) / "hubs.geojson"
        return build_od_routes(self.config, hub_file)

    def generate_instance(self, params: InstanceParams) -> Path:
        output_dir = Path(self.config.output_dir)
        return generate_instance(
            od_routes_path=output_dir / "od_routes.json",
            stations_path=output_dir / "stations.json",
            hubs_geojson_path=output_dir / "hubs.geojson",
            output_dir=output_dir,
            params=params,
            seed=self.config.seed,
        )

    def run_all(self, params: InstanceParams) -> Path:
        stations_path = self.prepare_stations()
        hubs_path = self.build_hubs(stations_path)
        self.compute_routes(hubs_path)
        return self.generate_instance(params)
