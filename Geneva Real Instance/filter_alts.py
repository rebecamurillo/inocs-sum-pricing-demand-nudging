def filter_alternatives(A1, A2, B, max_travel_time=80):
    """
    Filter the alternative dictionaries as follows:
      1. Remove any alternative in A1 and A2 whose total_travel_time exceeds max_travel_time (80 minutes).
      2. Remove any O-D pair (i.e. key) from A1, A2, and B if that O-D pair has no alternative 
         in either A1 or A2.
    
    Parameters:
      A1: dict keyed by (o, d) with PT+bike alternatives.
      A2: dict keyed by (o, d) with PT-only alternatives.
      B:  dict keyed by (o, d) with Car alternatives.
      max_travel_time: threshold (in minutes) beyond which alternatives are discarded.
    
    Returns:
      A tuple (filtered_A1, filtered_A2, filtered_B)
    """
    # Filter alternatives in A1: remove alternatives with total_travel_time > max_travel_time.
    filtered_A1 = {}
    for key, alternatives in A1.items():
        filtered_alts = [alt for alt in alternatives if alt.get("total_travel_time", float('inf')) <= max_travel_time]
        if filtered_alts:  # Only keep the key if there is at least one alternative remaining.
            filtered_A1[key] = filtered_alts

    # Do the same for A2.
    filtered_A2 = {}
    for key, alternatives in A2.items():
        filtered_alts = [alt for alt in alternatives if alt.get("total_travel_time", float('inf')) <= max_travel_time]
        if filtered_alts:
            filtered_A2[key] = filtered_alts

    # Determine which O-D keys still have alternatives in either A1 or A2.
    keys_to_keep = set(filtered_A1.keys()).union(set(filtered_A2.keys()))
    
    # Filter B to keep only keys that are in keys_to_keep.
    filtered_B = {key: alts for key, alts in B.items() if key in keys_to_keep}

    # Also ensure that filtered_A1 and filtered_A2 contain only keys in keys_to_keep (should be redundant).
    filtered_A1 = {key: alts for key, alts in filtered_A1.items() if key in keys_to_keep}
    filtered_A2 = {key: alts for key, alts in filtered_A2.items() if key in keys_to_keep}
    
    return filtered_A1, filtered_A2, filtered_B, keys_to_keep
