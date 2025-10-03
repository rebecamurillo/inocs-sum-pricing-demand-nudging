#precompute_direct_alternatives

import numpy as np

from math import sqrt

#Helper Euclidean Distance

def euclidean_distance(geom1, geom2):
    dx = geom1.x - geom2.x
    dy = geom1.y - geom2.y
    return sqrt(dx*dx + dy*dy)


# --- Precompute Direct PT Alternatives ---
def precompute_direct_pt_alternatives(nodes, scaling_pt=0.06):
    direct_alts = {}
    for o in nodes:
        for m in nodes:
            if o['hub_id'] == m['hub_id']:
                continue
            common_lines = set(o['lines']).intersection(set(m['lines']))
            if common_lines:
                dist = euclidean_distance(o['geometry'], m['geometry'])
                for line in common_lines:
                    arc = {
                        "pt_time": int(dist * scaling_pt),
                        "line": line,
                        "transfers": 0
                    }
                    key = (o['hub_id'], m['hub_id'])
                    if key not in direct_alts:
                        direct_alts[key] = []
                    direct_alts[key].append(arc)
    return direct_alts

# --- Precompute Direct Bike Alternatives ---
def precompute_direct_bike_alternatives(nodes, scaling_bike=0.04):
    bike_alts = {}
    bike_nodes = [n for n in nodes if "bike" in n['label'].lower()]
    for o in bike_nodes:
        for m in bike_nodes:
            if o['hub_id'] == m['hub_id']:
                continue
            dist = euclidean_distance(o['geometry'], m['geometry'])
            alt = {
                "bike_time": int(dist * scaling_bike),
                "transfers": 0
            }
            key = (o['hub_id'], m['hub_id'])
            if key not in bike_alts:
                bike_alts[key] = []
            bike_alts[key].append(alt)
    return bike_alts