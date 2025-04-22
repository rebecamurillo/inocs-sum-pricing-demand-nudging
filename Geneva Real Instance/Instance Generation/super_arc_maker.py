import json
from collections import defaultdict

def make_super_arcs(input_path, output_path):
    """
    Reads JSON from input_path, replaces data['arcs_pt_only'] by a new set of
    super‑arcs per OD key, grouping all arcs with identical (pt_time, transfers)
    into one super‑arc that lists all of their line‑patterns.
    Writes the updated JSON to output_path.
    """
    # 1. load
    with open(input_path, 'r') as f:
        data = json.load(f)

    new_arcs_pt_only = {}

    for od_key, arc_list in data.get('arcs_pt_only', {}).items():
        # normalize each arc → always have arc['lines'] list & arc['transfer_nodes'] list
        norm = []
        for arc in arc_list:
            # build a uniform list-of-lines
            if 'lines' in arc:
                lines = arc['lines']
            elif 'line' in arc:
                lines = [arc['line']]
            else:
                lines = []
            # build a uniform list-of-transfer-nodes
            if 'transfer_nodes' in arc:
                tnodes = arc['transfer_nodes']
            elif 'transfer_node' in arc:
                tnodes = [arc['transfer_node']]
            else:
                tnodes = []

            norm.append({
                'pt_time':     arc['pt_time'],
                'transfers':   arc['transfers'],
                'lines':       lines,
                'transfer_nodes': tnodes
            })

        # group by (pt_time, transfers)
        groups = defaultdict(list)
        for arc in norm:
            key = (arc['pt_time'], arc['transfers'])
            groups[key].append(arc)

        # build super-arcs
        super_arcs = []
        for idx, ((pt_time, transfers), members) in enumerate(groups.items(), start=1):
            # collect all distinct line‐patterns and transfer‐nodes patterns
            lines_options = [m['lines'] for m in members]
            tnodes_options = [m['transfer_nodes'] for m in members] if any(m['transfer_nodes'] for m in members) else None

            super_arc = {
                'arc_id':              f"super_{od_key}_{idx}",
                'pt_time':             pt_time,
                'transfers':           transfers,
                'lines_options':       lines_options
            }
            if tnodes_options is not None:
                super_arc['transfer_nodes_options'] = tnodes_options

            super_arcs.append(super_arc)

        new_arcs_pt_only[od_key] = super_arcs

    # replace and save
    data['arcs_pt_only'] = new_arcs_pt_only
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=4)

    print(f"Super‑arc data written to {output_path}")



