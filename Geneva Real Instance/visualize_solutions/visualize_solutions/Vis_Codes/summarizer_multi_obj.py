<<<<<<< HEAD
import os, glob, json, pandas as pd, numpy as np

def summarise_multiobj_solutions(solution_input: str, L: int = 7) -> pd.DataFrame:
    """Summarise every *_solution.json* found in a folder OR a single file.

    Works for an arbitrary number of objectives stored under the key
    "Objectives": {name: value, ...}.  If that key is absent the legacy
    two-objective fields are used.
    """
    # ------------------------------------------------------------
    # 1. collect files
    # ------------------------------------------------------------
    if os.path.isdir(solution_input):
        paths = glob.glob(os.path.join(solution_input, '*solution*.json'))
        exp_name = os.path.basename(os.path.normpath(solution_input))
    elif os.path.isfile(solution_input):
        paths = [solution_input]
        exp_name = os.path.basename(solution_input)
    else:
        raise ValueError("Must point to a folder or to a single .json file")

    # ------------------------------------------------------------
    # 2. iterate
    # ------------------------------------------------------------
    summaries = []

    for fpath in paths:
        with open(fpath) as f:
            data = json.load(f)

        # ---------- objective values (flexible) -----------------
        obj_vals = {}
        if "Objectives" in data:                        # NEW format
            obj_vals = data["Objectives"]
        else:                                           # OLD format
            obj_vals = {
                "Primary"  : data.get("Primary Objective Value",  np.nan),
                "Secondary": data.get("Secondary Objective Value",np.nan)
            }

        # ---------- gaps, if present ---------------------------
        gap_vals = {}
        for k in ("Primary Gap (%)", "Secondary Gap (%)"):
            if k in data:
                gap_vals[k.replace(" Gap (%)", " Gap %")] = data[k]

        # ---------- instance metrics ---------------------------
        df_inst = pd.DataFrame(data.get("instances", []))
        instance_name = os.path.basename(fpath).replace("_solution.json", "")

        num_od     = df_inst["OD"].nunique()           if "OD" in df_inst else np.nan
        tot_demand = df_inst["Flow (q)"].sum()         if "Flow (q)" in df_inst else np.nan

        # ---------- robust aggregation: check both columns exist --------------
        if {"Type", "Flow (q)"} <= set(df_inst.columns):
            tot_car      = df_inst.loc[df_inst["Type"] == "Car",       "Flow (q)"].sum()
            tot_pt_a2    = df_inst.loc[df_inst["Type"] == "PT-Only",   "Flow (q)"].sum()
            tot_pt_a1    = df_inst.loc[df_inst["Type"] == "PT+Bike",   "Flow (q)"].sum()
        else:
            tot_car = tot_pt_a2 = tot_pt_a1 = np.nan


        summary_row = {
            "Instance":           instance_name,
            "Solve time (s)":     round(data.get("Solution Time (s)", 0), 2),
            "OD pairs":           num_od,
            "Total demand":       tot_demand,
            "Flow car":           tot_car,
            "Flow PT-only":       tot_pt_a2,
            "Flow PT+Bike":       tot_pt_a1,
            **obj_vals,          # ← one column per objective
            **gap_vals           # ← optional gaps
        }

        summaries.append(summary_row)

    # ------------------------------------------------------------
    # 3. assemble dataframe & nice order
    # ------------------------------------------------------------
    summary_df = pd.DataFrame(summaries)

    # put objective columns next to each other
    obj_cols = [c for c in summary_df.columns if c not in
                ["Instance", "Solve time (s)", "OD pairs", "Total demand",
                 "Flow car", "Flow PT-only", "Flow PT+Bike"]]
    fixed_cols = ["Instance", "Solve time (s)",
                  *obj_cols,
                  "OD pairs", "Total demand",
                  "Flow car", "Flow PT-only", "Flow PT+Bike"]
    summary_df = summary_df[fixed_cols]

    caption = f"Summary of solved instances (L={L}, exp={exp_name})"
    
    disp = display(summary_df.style.set_caption(caption))
        
    return disp
=======
import os, glob, json, pandas as pd, numpy as np

def summarise_multiobj_solutions(solution_input: str, L: int = 7) -> pd.DataFrame:
    """Summarise every *_solution.json* found in a folder OR a single file.

    Works for an arbitrary number of objectives stored under the key
    "Objectives": {name: value, ...}.  If that key is absent the legacy
    two-objective fields are used.
    """
    # ------------------------------------------------------------
    # 1. collect files
    # ------------------------------------------------------------
    if os.path.isdir(solution_input):
        paths = glob.glob(os.path.join(solution_input, '*solution*.json'))
        exp_name = os.path.basename(os.path.normpath(solution_input))
    elif os.path.isfile(solution_input):
        paths = [solution_input]
        exp_name = os.path.basename(solution_input)
    else:
        raise ValueError("Must point to a folder or to a single .json file")

    # ------------------------------------------------------------
    # 2. iterate
    # ------------------------------------------------------------
    summaries = []

    for fpath in paths:
        with open(fpath) as f:
            data = json.load(f)

        # ---------- objective values (flexible) -----------------
        obj_vals = {}
        if "Objectives" in data:                        # NEW format
            obj_vals = data["Objectives"]
        else:                                           # OLD format
            obj_vals = {
                "Primary"  : data.get("Primary Objective Value",  np.nan),
                "Secondary": data.get("Secondary Objective Value",np.nan)
            }

        # ---------- gaps, if present ---------------------------
        gap_vals = {}
        for k in ("Primary Gap (%)", "Secondary Gap (%)"):
            if k in data:
                gap_vals[k.replace(" Gap (%)", " Gap %")] = data[k]

        # ---------- instance metrics ---------------------------
        df_inst = pd.DataFrame(data.get("instances", []))
        instance_name = os.path.basename(fpath).replace("_solution.json", "")

        num_od     = df_inst["OD"].nunique()           if "OD" in df_inst else np.nan
        tot_demand = df_inst["Flow (q)"].sum()         if "Flow (q)" in df_inst else np.nan

        # ---------- robust aggregation: check both columns exist --------------
        if {"Type", "Flow (q)"} <= set(df_inst.columns):
            tot_car      = df_inst.loc[df_inst["Type"] == "Car",       "Flow (q)"].sum()
            tot_pt_a2    = df_inst.loc[df_inst["Type"] == "PT-Only",   "Flow (q)"].sum()
            tot_pt_a1    = df_inst.loc[df_inst["Type"] == "PT+Bike",   "Flow (q)"].sum()
        else:
            tot_car = tot_pt_a2 = tot_pt_a1 = np.nan


        summary_row = {
            "Instance":           instance_name,
            "Solve time (s)":     round(data.get("Solution Time (s)", 0), 2),
            "OD pairs":           num_od,
            "Total demand":       tot_demand,
            "Flow car":           tot_car,
            "Flow PT-only":       tot_pt_a2,
            "Flow PT+Bike":       tot_pt_a1,
            **obj_vals,          # ← one column per objective
            **gap_vals           # ← optional gaps
        }

        summaries.append(summary_row)

    # ------------------------------------------------------------
    # 3. assemble dataframe & nice order
    # ------------------------------------------------------------
    summary_df = pd.DataFrame(summaries)

    # put objective columns next to each other
    obj_cols = [c for c in summary_df.columns if c not in
                ["Instance", "Solve time (s)", "OD pairs", "Total demand",
                 "Flow car", "Flow PT-only", "Flow PT+Bike"]]
    fixed_cols = ["Instance", "Solve time (s)",
                  *obj_cols,
                  "OD pairs", "Total demand",
                  "Flow car", "Flow PT-only", "Flow PT+Bike"]
    summary_df = summary_df[fixed_cols]

    caption = f"Summary of solved instances (L={L}, exp={exp_name})"
    
    disp = display(summary_df.style.set_caption(caption))
        
    return disp
>>>>>>> 1655082a5d8beda6aae5106606ff18724c579722
