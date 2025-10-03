import json
import sys
from collections import defaultdict

def clean_data(input_path, output_path):
    """
    Reads JSON from input_path, cleans arcs_pt_only and arcs_pt_bike as specified,
    and writes the cleaned JSON to output_path.
    it cleans the following:
    1) Remove waiting_time & total_travel_time from all PT arcs
    2) Filter arcs_pt_only: drop any transferred arc whose 'lines' list has duplicates
    3) Deduplicate arcs_pt_bike by (pt_time, bike_time, transfers, mile_type, transfer_node(s))
    """
    # 1) Load
    with open(input_path, 'r') as f:
        data = json.load(f)

    # 2) Remove waiting_time & total_travel_time from all PT arcs
    for section in ('arcs_pt_only', 'arcs_pt_bike'):
        for od, arc_list in data.get(section, {}).items():
            for arc in arc_list:
                arc.pop('waiting_time', None)
                arc.pop('total_travel_time', None)

    # 3) Filter arcs_pt_only: drop any transferred arc whose 'lines' list has duplicates
    cleaned_pt_only = {}
    for od, arc_list in data.get('arcs_pt_only', {}).items():
        new_list = []
        for arc in arc_list:
            transfers = arc.get('transfers', 0)
            if transfers > 0 and 'lines' in arc:
                lines = arc['lines']
                if len(lines) != len(set(lines)):
                    # skip this redundant arc
                    continue
            new_list.append(arc)
        cleaned_pt_only[od] = new_list
    data['arcs_pt_only'] = cleaned_pt_only

    # 4) Deduplicate arcs_pt_bike by (pt_time, bike_time, transfers, mile_type, transfer_node(s))
    cleaned_pt_bike = {}
    for od, arc_list in data.get('arcs_pt_bike', {}).items():
        seen = {}
        others = []
        for arc in arc_list:
            transfers = arc.get('transfers', 0)
            pt_time   = arc.get('pt_time')
            bike_time = arc.get('bike_time')
            mile_type = arc.get('mile_type')
            if transfers == 1:
                key = (pt_time, bike_time, transfers, mile_type, arc.get('transfer_node'))
            elif transfers == 2:
                # ensure tuple for transfer_nodes
                key = (pt_time, bike_time, transfers, mile_type,
                       tuple(arc.get('transfer_nodes', [])))
            else:
                # no dedup rule for other transfer counts
                others.append(arc)
                continue

            if key not in seen:
                seen[key] = arc
        # combine deduped ones with the 'others'
        cleaned_pt_bike[od] = list(seen.values()) + others

    data['arcs_pt_bike'] = cleaned_pt_bike

    # 5) Write back
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=4)
    print(f"Cleaned data written to {output_path}")