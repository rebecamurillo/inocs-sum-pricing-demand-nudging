
# --- Delta Calculation in Chunks ---
def compute_delta_A1_v2_in_chunks(A1, stations_list, chunk_size=100):
    delta = {}
    keys = list(A1.keys())
    for i in range(0, len(keys), chunk_size):
        chunk_keys = keys[i:i+chunk_size]
        for key in chunk_keys:
            origin = key[0]
            destination = key[1]
            for arc in A1[key]:
                arc_id = arc["arc_id"]
                mile_type = arc.get("mile_type", "").lower()
                if mile_type == "first":
                    if "transfer_node" in arc:
                        i_in = origin
                        i_out = arc["transfer_node"]
                    elif "transfer_nodes" in arc:
                        i_in = origin
                        i_out = arc["transfer_nodes"][0]
                    else:
                        continue
                elif mile_type == "last":
                    if "transfer_node" in arc:
                        i_in = arc["transfer_node"]
                        i_out = destination
                    elif "transfer_nodes" in arc:
                        i_in = arc["transfer_nodes"][-1]
                        i_out = destination
                    else:
                        continue
                else:
                    continue
                for station in stations_list:
                    if station == i_in:
                        delta[(station, arc_id)] = -1
                    elif station == i_out:
                        delta[(station, arc_id)] = +1
                    else:
                        delta[(station, arc_id)] = 0
    return delta