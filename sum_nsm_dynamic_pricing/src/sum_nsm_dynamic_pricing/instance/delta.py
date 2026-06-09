# Source: Geneva_Complete_Link_Instances_and_Optimization/OTP2_Geneva_Instances/API_call_instance_generation_instance_validation.ipynb

def compute_delta_ia(arcs_pt_bike: dict, name_to_id: dict[str, str]) -> dict:
    delta_ia = {}
    for arc_list in arcs_pt_bike.values():
        for arc in arc_list:
            arc_id = arc["arc_id"]
            delta = {}
            for leg in arc.get("legs", []):
                if leg.get("mode") != "BICYCLE":
                    continue
                from_name = leg.get("from_place", "").strip().lower()
                to_name = leg.get("to_place", "").strip().lower()
                sid_out = name_to_id.get(from_name)
                sid_in = name_to_id.get(to_name)
                if sid_out is not None:
                    delta[sid_out] = delta.get(sid_out, 0) - 1
                if sid_in is not None:
                    delta[sid_in] = delta.get(sid_in, 0) + 1
            if delta:
                delta_ia[arc_id] = delta
    return delta_ia
