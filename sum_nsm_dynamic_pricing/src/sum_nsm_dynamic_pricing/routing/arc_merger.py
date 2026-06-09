# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb
from pathlib import Path

from ..utils.io import read_json, write_json


def prefix_arc_ids(od_routes_path: Path) -> Path:
    payload = read_json(Path(od_routes_path))
    for od in payload.get("od_results", []):
        for arc in od.get("arc_pt_bike", []):
            arc["arc_id"] = f"a_mm_{arc['arc_id']}"
        for arc in od.get("arc_pt_only", []):
            arc["arc_id"] = f"a_pt_{arc['arc_id']}"
        for arc in od.get("arc_car", []):
            arc["arc_id"] = f"c_{arc['arc_id']}"

    target = Path(od_routes_path).with_name("od_routes_prefixed.json")
    write_json(target, payload)
    return target
