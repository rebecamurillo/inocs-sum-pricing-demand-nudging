from pathlib import Path

from sum_nsm_dynamic_pricing import InstancePipeline, InstanceParams, PipelineConfig
from sum_nsm_dynamic_pricing.stations.providers import DonkeyRepublicProvider


def main() -> None:
    config = PipelineConfig(
        center_lat=46.2044,
        center_lon=6.1432,
        radius_m=2000,
        output_dir=Path("./output_geneva"),
        gtfs_path=Path("./tpg_gtfs.zip"),
        gbfs_path=None,
        seed=42,
    )

    pipeline = InstancePipeline(config=config, gbfs_provider=DonkeyRepublicProvider())
    instance_path = pipeline.run_all(InstanceParams())
    print(f"Instance generated at: {instance_path}")


if __name__ == "__main__":
    main()
