import os
import glob
import json
import pandas as pd
import numpy as np

def summarize_experiment_solutions(solution_input, L=7, show=True):
    """
    Processes all solution JSON files in the given folder and returns a summary DataFrame.
    
    The function looks for all JSON files in the folder that have "solution" in their filename, or a given path to the solution file,
    then for each file, it extracts key metrics such as solution time, objective value, gap,
    number of OD pairs, total demand, flows, average bike price, average transfers, and more.
    It also computes usage ratios for PT Only and Multimodal arcs.
    
    Parameters:
      solution_input (str): Either a folder path containing solution JSON files, or a path to a single solution JSON file.
      L (int): A label or parameter included in the summary caption.

    Returns:
      summary_df (pandas.DataFrame): A DataFrame summarizing key metrics for each solution instance.
    """
# Determine if the input is a folder or a single file
    if os.path.isdir(solution_input):
        solution_paths = glob.glob(os.path.join(solution_input, '*solution*.json'))
        exp_name = os.path.basename(os.path.normpath(solution_input))
    elif os.path.isfile(solution_input):
        solution_paths = [solution_input]
        exp_name = os.path.basename(solution_input)
    else:
        raise ValueError("Invalid path provided. Must be a folder or a .json file.")
    
    # Store results from all solution files.
    all_summaries = []
    
    # Loop through all generated solution files.
    for solution_file in solution_paths:
        if os.path.exists(solution_file):
            with open(solution_file, "r") as f:
                data = json.load(f)
            
            # Extract key values.
            solution_time = round(data.get("Solution Time (s)", 0), 2)
            Gap = round(data.get("Gap (%)", 0), 2)
            
            # Convert the instances list to a DataFrame.
            df = pd.DataFrame(data.get("instances", []))
            
            # Extract instance name from the filename.
            instance_name = os.path.basename(solution_file).replace("_solution.json", "")
            
            # Compute key statistics.
            num_od_pairs = df["OD"].nunique() if "OD" in df.columns else np.nan
            total_demand = round(df["Flow (q)"].sum(), 2) if "Flow (q)" in df.columns else np.nan
            total_flow_car = round(df[df["Type"] == "Car"]["Flow (q)"].sum(), 2) if "Type" in df.columns else np.nan
            total_flow_pt_only = round(df[df["Type"] == "PT-Only"]["Flow (q)"].sum(), 2) if "Type" in df.columns else np.nan
            total_flow_pt_bike = round(df[(df["Type"] == "PT+Bike") & (df["Flow (q)"] >= 1)]["Flow (q)"].sum(), 2) if "Type" in df.columns else np.nan
            
            avg_bike_price_pt_bike = df[(df["Type"] == "PT+Bike") & (df["Flow (q)"] >= 1)]["Bike Price"].mean() if "Bike Price" in df.columns else np.nan
            avg_bike_price_pt_bike_total = df[(df["Type"] == "PT+Bike") & (df["nu"] == 1)]["Bike Price"].mean() if "nu" in df.columns and "Bike Price" in df.columns else np.nan
            avg_num_transfers_pt_bike = df[(df["Type"] == "PT+Bike") & (df["Flow (q)"] >= 1)]["Transfers"].mean() if "Transfers" in df.columns else np.nan
            avg_num_transfers_pt_only = df[(df["Type"] == "PT-Only") & (df["Flow (q)"] >= 1)]["Transfers"].mean() if "Transfers" in df.columns else np.nan
            
            total_pt_only_arcs = df[df["Type"] == "PT-Only"].shape[0] if "Type" in df.columns else np.nan
            total_pt_bike_arcs = df[df["Type"] == "PT+Bike"].shape[0] if "Type" in df.columns else np.nan
            used_pt_only_arcs = df[(df["Type"] == "PT-Only") & (df["Flow (q)"] >= 1)].shape[0] if "Type" in df.columns else np.nan
            used_pt_bike_arcs = df[(df["Type"] == "PT+Bike") & (df["Flow (q)"] >= 1)].shape[0] if "Type" in df.columns else np.nan
            relax_difs_max = df[df["Type"] == "PT+Bike"]["Relaxation Difference"].max() if "Relaxation Difference" in df.columns else np.nan
            relax_difs_min = df[df["Type"] == "PT+Bike"]["Relaxation Difference"].min() if "Relaxation Difference" in df.columns else np.nan
            z_values_max = round(df[df["Type"] == "PT+Bike"]["z value"].max(), 2) if "z value" in df.columns else np.nan
            z_values_min = round(df[df["Type"] == "PT+Bike"]["z value"].min(), 2) if "z value" in df.columns else np.nan
            price_max = df[df["Type"] == "PT+Bike"]["Bike Price"].max() if "Bike Price" in df.columns else np.nan
            price_min = df[(df["Type"] == "PT+Bike") & (df["Bike Price"] > 0.1)]["Bike Price"].min() if "Bike Price" in df.columns else np.nan
            
            # Define your assumed bike cost
            bike_cost = 0.5  # Update as needed

            # Filter for relevant rows
            pt_bike_rows = df[(df["Type"] == "PT+Bike") & (df["Flow (q)"] > 0)]

            # Calculate profit terms
            pt_bike_rows = pt_bike_rows.copy()
            pt_bike_rows["Approximated Profit"] = (
                pt_bike_rows["z value"] * pt_bike_rows["Bike Time"]
                - pt_bike_rows["Flow (q)"] * pt_bike_rows["Bike Time"] * bike_cost
            )
            pt_bike_rows["Profit"] = (
                pt_bike_rows["Flow (q)"] * pt_bike_rows["Bike Time"] * (pt_bike_rows["Bike Price"] - bike_cost)
            )

            # Sum profits for instance-level summary
            approximated_profit_total = pt_bike_rows["Approximated Profit"].sum()
            profit_total = pt_bike_rows["Profit"].sum()


            # Append summary dictionary.

            base_info = {"Instance Name": instance_name,
                "Solution Time (s)": solution_time}
            
            if data.get("Objective Value") or data.get("Primary Objective Value") is not None:
                obj_info = { "Obj Value": round(data.get("Objective Value", 0), 2) or round(data.get("Primary Objective Value", 0), 2)}
            else:
                objectives = data.get("Objectives", {})
                obj_info = {key: round(value, 2) for key, value in objectives.items()}


            stats_info = {
                "Gap (%)": Gap,
                "Approximated Profit": round(approximated_profit_total, 2),
                "Profit": round(profit_total, 2),
                "Relaxation Difference max": relax_difs_max,
                "Relaxation Difference min": relax_difs_min,
                "z_max": z_values_max,
                "z_min": z_values_min,            
                "p_max": price_max,
                "p_min": price_min,
                "Number of OD Pairs": num_od_pairs,
                "Total Demand": total_demand,
                "Total Flow (Car)": total_flow_car,
                "Total Flow (PT Only)": total_flow_pt_only,
                "Total Flow (Multimodal)": total_flow_pt_bike,
                "Avg Bike Price (for all offered arcs)": avg_bike_price_pt_bike_total,
                "Avg Bike Price (Multimodal, Flow ≥ 1)": avg_bike_price_pt_bike,
                "Avg Number of Transfers (PT Only)": avg_num_transfers_pt_only,
                "Avg Number of Transfers (Multimodal)": avg_num_transfers_pt_bike,
                "Total PT Only Arcs": total_pt_only_arcs,
                "Used PT Only Arcs (Flow >= 1)": used_pt_only_arcs,
                "Total Multimodal Arcs": total_pt_bike_arcs,
                "Used Multimodal Arcs (Flow >= 1)": used_pt_bike_arcs
            }
            summar = {**base_info, **obj_info, **stats_info}    
            all_summaries.append(summar)

    
    # Convert the summary list to a DataFrame.
    summary_df = pd.DataFrame(all_summaries)
    
    # Compute usage ratios.
    total_arcs = summary_df["Total PT Only Arcs"] + summary_df["Total Multimodal Arcs"]
    summary_df["PT Only Arcs Usage Ratio"] = summary_df["Used PT Only Arcs (Flow >= 1)"] / total_arcs
    summary_df["Multimodal Arcs Usage Ratio"] = summary_df["Used Multimodal Arcs (Flow >= 1)"] / total_arcs
    
    # Optionally, you can also melt the DataFrame to long format for plotting usage ratios.
    usage_cols = ["PT Only Arcs Usage Ratio", "Multimodal Arcs Usage Ratio"]
    df_usage = summary_df.melt(
        id_vars=["Instance Name"],
        value_vars=usage_cols,
        var_name="Arc Type",
        value_name="Usage Ratio"
    )
    if show:
        display(summary_df.style.set_caption(f"Summary of Solved Instances From Real Network with L={L}, {exp_name} "))
    
    return summary_df


