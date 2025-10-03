def clean_alternatives_and_make_them_super(A1_dict, A2_dict, build_super_arcs=True):
    """
    Deduplicate PT‑bike arcs (A1_dict) and PT‑only arcs (A2_dict) *in place*.

    Parameters
    ----------
    A1_dict : dict[(origin, dest)] -> list[arc]
    A2_dict : dict[(origin, dest)] -> list[arc]
    build_super_arcs : bool
        If True, A2_dict is replaced by one super‑arc per (pt_time, transfers)
        group.  If False, just drops arcs whose 'lines' list contains duplicates.

    Returns
    -------
    A1_dict_clean, A2_dict_clean
    """
    # ---- 1.  PT‑only -------------------------------------------------------
    cleaned_A2 = {}
    for od, arc_list in A2_dict.items():
        if build_super_arcs:
            groups = {}
            for arc in arc_list:
                key = (arc["pt_time"], arc["transfers"])
                groups.setdefault(key, []).append(arc)

            super_arcs = []
            for idx, ((pt_time, transfers), members) in enumerate(groups.items(), 1):
                lines_opts  = [m.get("lines", [])  for m in members]
                tnode_opts  = [m.get("transfer_nodes", m.get("transfer_node", []))
                               for m in members]
                super_arc = {
                    "arc_id":            f"super_{od[0]}_{od[1]}_{idx}",
                    "pt_time":           pt_time,
                    "transfers":         transfers,
                    "lines_options":     lines_opts
                }
                if any(tnode_opts):
                    super_arc["transfer_nodes_options"] = tnode_opts
                super_arcs.append(super_arc)
            cleaned_A2[od] = super_arcs
        else:
            new_list = []
            for arc in arc_list:
                if arc.get("transfers", 0) > 0 and "lines" in arc:
                    if len(arc["lines"]) != len(set(arc["lines"])):
                        continue            # drop duplicate‑line arc
                new_list.append(arc)
            cleaned_A2[od] = new_list

    # ---- 2.  PT+Bike -------------------------------------------------------
    cleaned_A1 = {}
    for od, arc_list in A1_dict.items():
        seen, others = {}, []
        for arc in arc_list:
            t   = arc.get("transfers", 0)
            key = None
            if t == 1:
                key = (arc["pt_time"], arc["bike_time"], t,
                       arc.get("mile_type"), arc.get("transfer_node"))
            elif t == 2:
                key = (arc["pt_time"], arc["bike_time"], t,
                       arc.get("mile_type"),
                       tuple(arc.get("transfer_nodes", [])))
            if key is None:
                others.append(arc)
            elif key not in seen:
                seen[key] = arc
        cleaned_A1[od] = list(seen.values()) + others

    return cleaned_A1, cleaned_A2
