# sum_nsm_dynamic_pricing

A Python library to generate optimization-ready mobility instances from GTFS and GBFS data, run
OTP-based routing, solve the bilevel dynamic-pricing optimization model, and export summary metrics.

> For the full demo — sample data, the demo notebook, and the model document — see the
> [repository root README](../README.md).

## Requirements

- Python 3.10+
- Gurobi with an active license (`gurobipy` is a required dependency)
- OpenTripPlanner running and reachable from your machine

## Install

```bash
python -m pip install -e .
```

This installs the package in editable mode for local development.

## Usage

```python
from pathlib import Path

from sum_nsm_dynamic_pricing import (
    DonkeyRepublicProvider,
    InstanceParams,
    InstancePipeline,
    OptimizerParams,
    PipelineConfig,
)

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
solution_path = pipeline.optimize(OptimizerParams(), instance_path=instance_path)
metrics_path = pipeline.summarize_optimization(solution_path, params)
```

A runnable version of this is in [examples/geneva_pipeline.py](examples/geneva_pipeline.py):

```bash
python examples/geneva_pipeline.py
```

## Build

```bash
python -m pip install --upgrade build
python -m build
```

Artifacts are written to `dist/`. Install the wheel with `python -m pip install dist/*.whl`.
