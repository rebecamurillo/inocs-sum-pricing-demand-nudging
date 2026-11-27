"""Runs the package's `build_od_routes` alone, in the interpreter that runs this file, with the
demonstrator's retry policy mounted: the characterisation tests start it as a subprocess so
that the pytest process never imports the package, and so that every run starts a fresh option
counter (as a resumed build does).

Usage: `routes_probe.py <folder> <otp_url> <retries> <retry_wait_s>`; the folder holds
`hubs.geojson` (and the `od_cache.json` of an earlier run, when resuming). Prints the routes
file's `od_results` as JSON on stdout.
"""

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    from sum_nsm_dynamic_pricing.config import PipelineConfig
    from sum_nsm_dynamic_pricing.routing.otp_client import OTPClient
    from sum_nsm_dynamic_pricing.routing.route_builder import build_od_routes

    from pricing_demo.infrastructure.pricing_model.retry_policy import mounted_on_otp_clients

    folder = Path(argv[0])
    config = PipelineConfig(
        0.0,
        0.0,
        0.0,
        folder,
        folder / "unused.zip",
        otp_url=argv[1],
        min_od_distance_m=500.0,
        otp_timestamp="2025-03-10T08:30:00.000000Z",
    )
    with mounted_on_otp_clients(OTPClient, int(argv[2]), float(argv[3])):
        routes = build_od_routes(config, folder / "hubs.geojson")
    results = json.loads(routes.read_text(encoding="utf-8"))["od_results"]
    sys.stdout.write(json.dumps(results))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
