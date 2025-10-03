from pathlib import Path
import pandas as pd
import json

def summarize_base_case_LL_experiments(base_case_save_folder, show = True):
    """
    Summarizes the results of base case LL experiments.
    
    Parameters:
    - base_case_save_folder: Path to the folder containing the solution files.
    - show: If True, displays the summary DataFrame.
    
    Returns:
    - summary_df: DataFrame containing the summarized results.
    """
    


    # --------------------------------------------------------------------
    # 2.  Collect the summary rows
    # --------------------------------------------------------------------
    rows = []
    for f in Path(base_case_save_folder).glob("*_LL_solution.json"):
        with open(f, "r") as fp:
            res = json.load(fp)

        # ----------------- robust extraction ----------------------------
        flow_totals = res.get("flow_totals", {})
        if not flow_totals and "flows" in res:           # older output format
            # rebuild quick totals
            pt_bike = sum(x["q"] for x in res["flows"] if x.get("type") == "PT+Bike")
            pt_only = sum(x["q"] for x in res["flows"] if x.get("type") == "PT")
            car     = sum(x["q"] for x in res["flows"] if x.get("type") == "Car")
            flow_totals = {"PT+Bike": pt_bike, "PT": pt_only, "Car": car}

        rows.append({
            "Instance Name"             : f.stem,
            "Solution Time (s)"         : res.get("solution_time", None),   # only if you stored it
            "Gap (%)"                   : res.get("gap", None),             # same – may be None
            "Objective"                 : res.get("objective"),
            "Total Flow (Multimodal)"   : flow_totals.get("PT+Bike", 0),
            "Total Flow (PT Only)"      : flow_totals.get("PT", 0),
            "Total Flow (Car)"          : flow_totals.get("Car", 0),
            "Revenue"                   : res.get("revenue", 0)
        })

    # --------------------------------------------------------------------
    # 3.  Build and show the dataframe
    # --------------------------------------------------------------------
    df = pd.DataFrame(rows).set_index("Instance Name")
    if show:
        display(df.style.set_caption("Summary of Base Case LL Experiments"))
    return df     # if running in Jupyter; otherwise print(df)