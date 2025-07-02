<<<<<<< HEAD
import json, os, pathlib, statistics, math
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import display

from Codes.CPPMTO_optimizer1_weighted_sum_variant_MOO import (
        solve_bilevel_model_weighted_sum_variant_MOO)
from visualize_solutions.Bilevel_Solution_Visualization import (
        summarize_experiment_solutions)


# ──────────────────────────────────────────────────────────────
# main driver – weighted-sum Pareto sweep
# ──────────────────────────────────────────────────────────────
def run_weighted_sum_analysis(instance_path,
                              save_folder,
                              w_grid = None,      # list/array of w1 (flow) weights
                              grid_size = 11):    # if w_grid is None use 0…1 grid
    os.makedirs(save_folder, exist_ok=True)



    # 1) ideal & nadir for normalisation inside the weighted solver
    _, (g1_I, g3_N), _ = solve_bilevel_model_weighted_sum_variant_MOO(
        instance_path, save_folder, mode="g1", verbose2=False)

    _, (g1_N, g3_I), _ = solve_bilevel_model_weighted_sum_variant_MOO(
        instance_path, save_folder, mode="g3", verbose2=False)

    print(f"Ideal (flow max, profit max) : ({g1_I:.0f} , {g3_I:.0f})")
    print(f"Nadir (flow min, profit min) : ({g1_N:.0f} , {g3_N:.0f})\n")

    # 2) build weight grid  w1∈[0,1] ,  w2 = 1-w1
    if w_grid is None:
        w_grid = np.linspace(0, 1, grid_size)      # uniform 0.00 … 1.00

    summary_rows = []

    for w1 in w_grid:
        w2 = 1 - w1
        print("")
        print(f"solving weight pair  w1={w1:.2f}  w2={w2:.2f}")
        print("")

        _, (g1, g3), _ = solve_bilevel_model_weighted_sum_variant_MOO(
            instance_path, save_folder, mode="weighted",
            weights=(w1, w2),
            ideal  =(g1_I, g3_I),
            nadir  =(g1_N, g3_N),
            verbose2=False)

        # grab KPIs from helper
        df_tmp = summarize_experiment_solutions(save_folder, show=False)
        row    = df_tmp.iloc[-1].copy()
        row["w1"] = w1
        row["w2"] = w2
        row["g1"] = g1
        row["g3"] = g3
        summary_rows.append(row)

    # 3) dataframe & save
    summary_df = (pd.DataFrame(summary_rows)
                  .sort_values("w1")
                  .reset_index(drop=True))
    display(summary_df)

    name = pathlib.Path(instance_path).stem
    ws_dir = os.path.join(save_folder, "ws_curves"); os.makedirs(ws_dir, exist_ok=True)
    json_path = os.path.join(ws_dir, f"ws_curve_{name}.json")
    summary_df.to_json(json_path, orient="records", indent=2)
    print(f"\n{len(summary_df)} weight runs stored → {json_path}")

    # 4) Pareto curve  (profit vs flow)
    plt.figure(figsize=(6,4))
    plt.scatter(
            summary_df["g3"],     # x-axis: profit
            summary_df["g1"],     # y-axis: flow
            marker="o",           # filled circle
            s=40,                 # dot size (adjust as you like)
            color="blue"         # any single colour; default is blue
            # edgecolors="none"   # optional—same effect as leaving it out
        )
    plt.xlabel("Profit  g3  ↑")
    plt.ylabel("Total flow  g1  ↑")
    plt.title(f"Weighted-sum Pareto sweep  ({name})")
    plt.tight_layout()
    plt.savefig(os.path.join(ws_dir, f"pareto_ws_{name}.png"))
    plt.show()

    secondary = "Profit"

    instance_name = name
    # 5) extra diagnostics (reuse your old helper)
    def plot_and_save(x, y, xlabel, ylabel, title, filename):
        plt.figure(figsize=(6,4))
        plt.scatter(x, y,             marker="o",           # filled circle
            s=40,                 # dot size (adjust as you like)
            color="blue"         # any single colour; default is blue
            # edgecolors="none"   # optional—same effect as leaving it out
        )
        plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title)
        plt.tight_layout()
        plt.savefig(os.path.join(ws_dir, filename)); plt.show(); plt.close()

    # Plot 1: Profit vs secondary
    plot_and_save(summary_df["g1"], summary_df["Profit"],
                  f"Flow", "Profit",
                  f"Flow vs Profit \nInstance: {name}", f"Flow_vs_Profit_{instance_name}.png")

    # Plot 2: Total Flow (Car) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (Car)"],
                  f"{secondary}", "Total Flow (Car)",
                  f"Total Flow (Car) vs {secondary}\nInstance: {instance_name}", f"car_flow_vs_{secondary}_{instance_name}.png")

    # Plot 3: Total Flow (PT Only) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (PT Only)"],
                  f"{secondary}", "Total Flow (PT Only)",
                  f"PT Flow vs {secondary}\nInstance: {instance_name}", f"pt_flow_vs_{secondary}_{instance_name}.png")

    # Plot 4: Total Flow (Multimodal) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (Multimodal)"],
                  f"{secondary}", "Total Flow (Multimodal)",
                  f"Multimodal Flow vs {secondary}\nInstance: {instance_name}", f"multimodal_flow_vs_{secondary}_{instance_name}.png")

    # Plot 5: Avg Bike Price (Multimodal, Flow ≥ 1) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Avg Bike Price (Multimodal, Flow ≥ 1)"],
                  f"{secondary}", "Avg Bike Price (Flow ≥ 1)",
                  f"Avg Bike Price vs {secondary}\nInstance: {instance_name}", f"avg_bike_price_vs_{secondary}_{instance_name}.png")

    # Plot 6: Total Flow (Multimodal) vs Total Flow (PT Only)
    plot_and_save(summary_df["Total Flow (PT Only)"], summary_df["Total Flow (Multimodal)"],
                  "Total Flow (PT Only)", "Total Flow (Multimodal)",
                  f"Multimodal vs PT Flow\nInstance: {instance_name}", f"multimodal_vs_pt_flow_{secondary}_{instance_name}.png")
    
    plot_and_save(summary_df["w1"], summary_df["Profit"],
                  "w1 (flow weight)", "Profit",
                  f"Profit vs weight  ({name})",
                  f"profit_vs_weight_{name}.png")
    
    plot_and_save(summary_df["w2"], summary_df["g1"],
                  "w2 (Profit weight)", "Flow",
                  f"Flow vs weight  ({name})",
=======
import json, os, pathlib, statistics, math
import numpy as np, pandas as pd, matplotlib.pyplot as plt
from IPython.display import display

from Codes.CPPMTO_optimizer1_weighted_sum_variant_MOO import (
        solve_bilevel_model_weighted_sum_variant_MOO)
from visualize_solutions.Bilevel_Solution_Visualization import (
        summarize_experiment_solutions)


# ──────────────────────────────────────────────────────────────
# main driver – weighted-sum Pareto sweep
# ──────────────────────────────────────────────────────────────
def run_weighted_sum_analysis(instance_path,
                              save_folder,
                              w_grid = None,      # list/array of w1 (flow) weights
                              grid_size = 11):    # if w_grid is None use 0…1 grid
    os.makedirs(save_folder, exist_ok=True)



    # 1) ideal & nadir for normalisation inside the weighted solver
    _, (g1_I, g3_N), _ = solve_bilevel_model_weighted_sum_variant_MOO(
        instance_path, save_folder, mode="g1", verbose2=False)

    _, (g1_N, g3_I), _ = solve_bilevel_model_weighted_sum_variant_MOO(
        instance_path, save_folder, mode="g3", verbose2=False)

    print(f"Ideal (flow max, profit max) : ({g1_I:.0f} , {g3_I:.0f})")
    print(f"Nadir (flow min, profit min) : ({g1_N:.0f} , {g3_N:.0f})\n")

    # 2) build weight grid  w1∈[0,1] ,  w2 = 1-w1
    if w_grid is None:
        w_grid = np.linspace(0, 1, grid_size)      # uniform 0.00 … 1.00

    summary_rows = []

    for w1 in w_grid:
        w2 = 1 - w1
        print("")
        print(f"solving weight pair  w1={w1:.2f}  w2={w2:.2f}")
        print("")

        _, (g1, g3), _ = solve_bilevel_model_weighted_sum_variant_MOO(
            instance_path, save_folder, mode="weighted",
            weights=(w1, w2),
            ideal  =(g1_I, g3_I),
            nadir  =(g1_N, g3_N),
            verbose2=False)

        # grab KPIs from helper
        df_tmp = summarize_experiment_solutions(save_folder, show=False)
        row    = df_tmp.iloc[-1].copy()
        row["w1"] = w1
        row["w2"] = w2
        row["g1"] = g1
        row["g3"] = g3
        summary_rows.append(row)

    # 3) dataframe & save
    summary_df = (pd.DataFrame(summary_rows)
                  .sort_values("w1")
                  .reset_index(drop=True))
    display(summary_df)

    name = pathlib.Path(instance_path).stem
    ws_dir = os.path.join(save_folder, "ws_curves"); os.makedirs(ws_dir, exist_ok=True)
    json_path = os.path.join(ws_dir, f"ws_curve_{name}.json")
    summary_df.to_json(json_path, orient="records", indent=2)
    print(f"\n{len(summary_df)} weight runs stored → {json_path}")

    # 4) Pareto curve  (profit vs flow)
    plt.figure(figsize=(6,4))
    plt.scatter(
            summary_df["g3"],     # x-axis: profit
            summary_df["g1"],     # y-axis: flow
            marker="o",           # filled circle
            s=40,                 # dot size (adjust as you like)
            color="blue"         # any single colour; default is blue
            # edgecolors="none"   # optional—same effect as leaving it out
        )
    plt.xlabel("Profit  g3  ↑")
    plt.ylabel("Total flow  g1  ↑")
    plt.title(f"Weighted-sum Pareto sweep  ({name})")
    plt.tight_layout()
    plt.savefig(os.path.join(ws_dir, f"pareto_ws_{name}.png"))
    plt.show()

    secondary = "Profit"

    instance_name = name
    # 5) extra diagnostics (reuse your old helper)
    def plot_and_save(x, y, xlabel, ylabel, title, filename):
        plt.figure(figsize=(6,4))
        plt.scatter(x, y,             marker="o",           # filled circle
            s=40,                 # dot size (adjust as you like)
            color="blue"         # any single colour; default is blue
            # edgecolors="none"   # optional—same effect as leaving it out
        )
        plt.xlabel(xlabel); plt.ylabel(ylabel); plt.title(title)
        plt.tight_layout()
        plt.savefig(os.path.join(ws_dir, filename)); plt.show(); plt.close()

    # Plot 1: Profit vs secondary
    plot_and_save(summary_df["g1"], summary_df["Profit"],
                  f"Flow", "Profit",
                  f"Flow vs Profit \nInstance: {name}", f"Flow_vs_Profit_{instance_name}.png")

    # Plot 2: Total Flow (Car) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (Car)"],
                  f"{secondary}", "Total Flow (Car)",
                  f"Total Flow (Car) vs {secondary}\nInstance: {instance_name}", f"car_flow_vs_{secondary}_{instance_name}.png")

    # Plot 3: Total Flow (PT Only) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (PT Only)"],
                  f"{secondary}", "Total Flow (PT Only)",
                  f"PT Flow vs {secondary}\nInstance: {instance_name}", f"pt_flow_vs_{secondary}_{instance_name}.png")

    # Plot 4: Total Flow (Multimodal) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (Multimodal)"],
                  f"{secondary}", "Total Flow (Multimodal)",
                  f"Multimodal Flow vs {secondary}\nInstance: {instance_name}", f"multimodal_flow_vs_{secondary}_{instance_name}.png")

    # Plot 5: Avg Bike Price (Multimodal, Flow ≥ 1) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Avg Bike Price (Multimodal, Flow ≥ 1)"],
                  f"{secondary}", "Avg Bike Price (Flow ≥ 1)",
                  f"Avg Bike Price vs {secondary}\nInstance: {instance_name}", f"avg_bike_price_vs_{secondary}_{instance_name}.png")

    # Plot 6: Total Flow (Multimodal) vs Total Flow (PT Only)
    plot_and_save(summary_df["Total Flow (PT Only)"], summary_df["Total Flow (Multimodal)"],
                  "Total Flow (PT Only)", "Total Flow (Multimodal)",
                  f"Multimodal vs PT Flow\nInstance: {instance_name}", f"multimodal_vs_pt_flow_{secondary}_{instance_name}.png")
    
    plot_and_save(summary_df["w1"], summary_df["Profit"],
                  "w1 (flow weight)", "Profit",
                  f"Profit vs weight  ({name})",
                  f"profit_vs_weight_{name}.png")
    
    plot_and_save(summary_df["w2"], summary_df["g1"],
                  "w2 (Profit weight)", "Flow",
                  f"Flow vs weight  ({name})",
>>>>>>> 1655082a5d8beda6aae5106606ff18724c579722
                  f"flow_vs_weight_{name}.png")