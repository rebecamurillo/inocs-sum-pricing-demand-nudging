# SUM NSM Dynamic Pricing for Demand Nudging — Demo

A demo of the dynamic-pricing model developed for the SUM project. The model and methodology are
described in [CSI_Report_D1_Mesut_Can_Koseoglu.pdf](CSI_Report_D1_Mesut_Can_Koseoglu.pdf).

The core deliverable is the [`sum_nsm_dynamic_pricing`](sum_nsm_dynamic_pricing) Python package: it
generates optimization-ready mobility instances from GTFS and GBFS data, runs OpenTripPlanner-based
routing, solves the bilevel dynamic-pricing optimization model, and exports summary metrics.

## What it does

1. Build station inputs from GTFS and GBFS (`stations.json`).
2. Build multimodal hubs with clustering (`hubs.geojson`).
3. Query OpenTripPlanner (OTP) for OD routes (`od_routes.json`).
4. Build the optimization instance file (`Instance_*.json`).
5. Run the bilevel optimization (`optimization_instance_results.json`).
6. Compute summary metrics (`optimization_metrics.json`).

If OTP is unavailable, route generation and the downstream steps are blocked.

## Repository layout

| Path | Description |
| --- | --- |
| [`sum_nsm_dynamic_pricing/`](sum_nsm_dynamic_pricing) | The Python package — the core deliverable. |
| [`demo_sum_nsm_dynamic_pricing.ipynb`](demo_sum_nsm_dynamic_pricing.ipynb) | Demo notebook: optimization and metrics on a generated instance. |
| [`data/sum_nsm_dynamic_pricing/geneva_1km_mon08h/`](data/sum_nsm_dynamic_pricing/geneva_1km_mon08h) | Sample Geneva inputs and outputs (stations, hubs, instance, results, metrics, `web_demo/`). |
| [`CSI_Report_D1_Mesut_Can_Koseoglu.pdf`](CSI_Report_D1_Mesut_Can_Koseoglu.pdf) | Model document. |

## Requirements

- Python 3.10+
- Gurobi with an active license (`gurobipy` is a required dependency)
- OpenTripPlanner running and reachable from your machine

## Install

From the repository root:

```bash
cd sum_nsm_dynamic_pricing
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs the package in editable mode for local development.

## Quick run

Run the example pipeline script
([sum_nsm_dynamic_pricing/examples/geneva_pipeline.py](sum_nsm_dynamic_pricing/examples/geneva_pipeline.py)):

```bash
python sum_nsm_dynamic_pricing/examples/geneva_pipeline.py
```

The script runs instance generation, optimization, and metrics export. It expects a GTFS zip at
`./tpg_gtfs.zip` and writes outputs to `./output_geneva`.

For an interactive walkthrough of the optimization and metrics step, open
[demo_sum_nsm_dynamic_pricing.ipynb](demo_sum_nsm_dynamic_pricing.ipynb).

## Minimal API example

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

A one-call `run_pipeline(config, params)` helper is also exported for the instance-generation step.

## Core outputs

By default, outputs are written to the configured `output_dir`:

- `stations.json`
- `hubs.geojson`
- `od_routes.json`
- `Instance_*.json`
- `optimization_instance_results.json`
- `optimization_metrics.json`
- `gurobi/` (solver logs and model artifacts)

A complete example output set is included under
[data/sum_nsm_dynamic_pricing/geneva_1km_mon08h/](data/sum_nsm_dynamic_pricing/geneva_1km_mon08h).

## Build the package

From the repository root:

```bash
cd sum_nsm_dynamic_pricing
python -m pip install --upgrade build
python -m build
```

Build artifacts are generated in `sum_nsm_dynamic_pricing/dist/`. Install the wheel locally with:

```bash
python -m pip install dist/*.whl
```
