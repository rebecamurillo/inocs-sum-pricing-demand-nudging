# sum_nsm_dynamic_pricing

Standalone package to generate optimization-ready instance files from GTFS + GBFS data.

## Pipeline

1. Build `stations.json` from GTFS and GBFS inputs.
2. Build `hubs.geojson` via agglomerative clustering.
3. Build `od_routes.json` from OTP queries.
4. Build `instance.json` for optimization.

If OTP is unavailable, routing and downstream steps are blocked.
