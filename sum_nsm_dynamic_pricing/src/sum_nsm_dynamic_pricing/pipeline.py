from pathlib import Path
import json
import logging
from dataclasses import asdict

from .clustering.hub_builder import build_hubs
from .config import InstanceParams, OptimizerParams, PipelineConfig
from .instance.generator import generate_instance
from .optimizer import solve as solve_optimization
from .optimizer import summarize as summarize_optimization
from .quality import validate_instance, validate_od_routes, clean_incomplete_od_pairs
from .routing.route_builder import build_od_routes
from .stations.builder import build_stations
from .stations.providers.base import GBFSProvider


logger = logging.getLogger(__name__)


class InstancePipeline:
    def __init__(self, config: PipelineConfig, gbfs_provider: GBFSProvider | None = None):
        self.config = config
        self.gbfs_provider = gbfs_provider

    def prepare_stations(self) -> Path:
        return build_stations(self.config, self.gbfs_provider)

    def build_hubs(self, stations_path: Path | None = None) -> Path:
        stations_file = stations_path or Path(
            self.config.output_dir) / "stations.json"
        hubs_path, _, _ = build_hubs(stations_file, self.config)
        return hubs_path

    def compute_routes(self, hubs_path: Path | None = None) -> Path:
        hub_file = hubs_path or Path(self.config.output_dir) / "hubs.geojson"
        routes_path = build_od_routes(self.config, hub_file)
        return routes_path

    def quality_routes(self, routes_path: Path) -> bool:
        if not validate_od_routes(routes_path):
            logger.warning(
                "Route quality validation reported issues. See error logs for details.")
            logger.warning(
                "Attempting to clean incomplete OD pairs and re-validate...")
            clean_incomplete_od_pairs(routes_path)

        return validate_od_routes(routes_path)

    def generate_instance(self, params: InstanceParams) -> Path:
        output_dir = Path(self.config.output_dir)
        instance_path = generate_instance(
            od_routes_path=output_dir / "od_routes.json",
            stations_path=output_dir / "stations.json",
            hubs_geojson_path=output_dir / "hubs.geojson",
            output_dir=output_dir,
            params=params,
            seed=self.config.seed,
        )
        if not validate_instance(instance_path):
            logger.warning(
                "Instance quality validation reported issues. See error logs for details.")
        return instance_path

    def run_all(self, params: InstanceParams) -> Path:
        stations_path = self.prepare_stations()
        hubs_path = self.build_hubs(stations_path)
        routes_path = self.compute_routes(hubs_path)
        self.quality_routes(routes_path)
        return self.generate_instance(params)

    def optimize(self, params: OptimizerParams, instance_path: Path | None = None) -> Path:
        output_dir = Path(self.config.output_dir)
        instance_file = instance_path or next(
            output_dir.glob("Instance_*.json"), None)
        if instance_file is None:
            raise FileNotFoundError(
                "No instance file found in output_dir. Run generate_instance first.")

        _, results_path = solve_optimization(
            instance_path=instance_file,
            output_dir=output_dir,
            max_displayed_alternatives=params.max_displayed_alternatives,
            mult_A1=params.mult_A1,
            capacity=params.capacity,
            inventory_level=params.inventory_level,
            dep_cost=params.dep_cost,
            cost_bike=params.cost_bike,
            parking_fee=params.parking_fee,
            P_bar=params.P_bar,
            pt_price=params.pt_price,
            theta=params.theta,
            ridership_weight=params.ridership_weight,
            sol_method=params.sol_method,
            verbose=params.verbose,
            verbose2=params.verbose2,
        )
        return results_path

    def summarize_optimization(self, solution_input: Path | None = None, params: OptimizerParams | None = None) -> Path:
        output_dir = Path(self.config.output_dir)
        solution_file = solution_input or (
            output_dir / "optimization_instance_results.json")
        summary_df = summarize_optimization(solution_file)
        metrics_path = output_dir / "optimization_metrics.json"
        records = summary_df.to_dict(orient="records")
        optimization_metrics = records[0] if len(records) == 1 else {"records": records}
        optimization_parameters = asdict(params or OptimizerParams())
        instance_config = asdict(self.config)
        # Paths are not JSON-serialisable; convert to strings.
        instance_config = {
            k: str(v) if isinstance(v, Path) else v
            for k, v in instance_config.items()
        }
        payload = {
            "instance_config": instance_config,
            "optimization_parameters": optimization_parameters,
            "optimization_metrics": optimization_metrics,
        }
        with metrics_path.open("w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)
        return metrics_path
