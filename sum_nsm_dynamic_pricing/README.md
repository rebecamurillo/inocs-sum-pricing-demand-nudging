# sum_nsm_dynamic_pricing

A Python library to generate optimization-ready mobility instances from GTFS and GBFS data, run OTP-based routing, solve the dynamic pricing optimization model, and export summary metrics.

## What the library does

Main process:
1. Build station inputs from GTFS and GBFS (`stations.json`).
2. Build multimodal hubs with clustering (`hubs.geojson`).
3. Query OpenTripPlanner (OTP) for OD routes (`od_routes.json`).
4. Build optimization instance file (`Instance_*.json`).
5. Run bilevel optimization (`optimization_instance_results.json`).
6. Compute summary metrics (`optimization_metrics.json`).

If OTP is unavailable, route generation and downstream steps are blocked.

## Requirements

- Python 3.10+
- Gurobi with an active license (`gurobipy` is a required dependency)
- OpenTripPlanner running and reachable from your machine

## Install locally

From repository root:

```bash
cd sum_nsm_dynamic_pricing
python -m pip install --upgrade pip
python -m pip install -e .
```

This installs the package in editable mode for local development.

## Quick local run

Use the example script in [sum_nsm_dynamic_pricing/examples/geneva_pipeline.py](sum_nsm_dynamic_pricing/examples/geneva_pipeline.py):

```bash
python sum_nsm_dynamic_pricing/examples/geneva_pipeline.py
```

The script runs instance generation, optimization, and metrics export.

## Build the package

From repository root:

```bash
cd sum_nsm_dynamic_pricing
python -m pip install --upgrade build
python -m build
```

Build artifacts are generated in:
- `sum_nsm_dynamic_pricing/dist/`

Install the wheel locally:

```bash
python -m pip install dist/*.whl
```

## Core outputs

By default, outputs are written to the configured `output_dir`:
- `stations.json`
- `hubs.geojson`
- `od_routes.json`
- `Instance_*.json`
- `optimization_instance_results.json`
- `optimization_metrics.json`
- `gurobi/` (solver logs and model artifacts)
