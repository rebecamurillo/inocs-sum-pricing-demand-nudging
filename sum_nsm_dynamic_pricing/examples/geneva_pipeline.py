from pathlib import Path

from sum_nsm_dynamic_pricing import (
    DonkeyRepublicProvider,
    InstanceParams,
    InstancePipeline,
    OptimizerParams,
    PipelineConfig,
)


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
    params = InstanceParams()
    instance_path = pipeline.run_all(params)
    print(f"Instance generated at: {instance_path}")

    solution_path = pipeline.optimize(OptimizerParams(), instance_path=instance_path)
    print(f"Optimization results saved at: {solution_path}")

    metrics_path = pipeline.summarize_optimization(solution_path, params)
    print(f"Optimization metrics saved at: {metrics_path}")


if __name__ == "__main__":
    main()
