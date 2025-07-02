import json, os, numpy as np
import matplotlib.pyplot as plt
from Codes.CPPMTO_optimizer1_epsilon_const_MOO_variant import solve_bilevel_model_epsilon_const_MOO_variant
from visualize_solutions.Bilevel_Solution_Visualization import summarize_experiment_solutions
from IPython.display import display
import pandas as pd

# ------------------------------------------------------------
# helper ─ extract bike_time statistics from a CPPMTO instance
# ------------------------------------------------------------
import json, pathlib, statistics, math

def get_bike_time_stats(json_path: str) -> dict:
    """Return {'count', 't_min', 't_avg'} from arcs_pt_bike in instance."""
    with pathlib.Path(json_path).open() as f:
        data = json.load(f)

    times = [arc["bike_time"]
             for arc_list in data.get("arcs_pt_bike", {}).values()
             for arc in arc_list]

    if not times:                      # defensive default
        return dict(count=0, t_min=math.inf, t_avg=math.inf)

    return dict(count=len(times),
                t_min=min(times),
                t_avg=statistics.mean(times))


def run_epsilon_constraint_variant_analysis(instance_path, save_folder, secondary="g2", step_mode="avg", delta_g1=1, delta_g2 = 0.5, m_steps=None, percent_step= None):
    os.makedirs(save_folder, exist_ok=True)

    """
    Build a δ accurate Pareto front with the ε-constraint method and
    adaptive bisection.

    Parameters
    ----------
    secondary : str
        Only 'obj_2' (profit) is implemented here.
    m_steps / percent_step
        Choose ONE of them to create the initial uniform grid.
    delta_g1 , delta_g2 : float
        Absolute tolerances for 'main' objective (total flow) and
        secondary objective (profit).  Reduce for a finer front.
    """
    #call helper to extract bike_time statistics

    # ─── auto ε step ─────────────────────────────────────────────
    stats      = get_bike_time_stats(instance_path)
    t_min      = stats["t_min"]          # minutes
    t_avg      = stats["t_avg"]          # minutes

    step_profit_min =  t_min * delta_g2     # strict lower bound
    step_profit_avg =  t_avg * delta_g2    # half-franc tick at average time

    if step_mode == "min":
        min_eps_step = step_profit_min
    elif step_mode == "avg":
        min_eps_step = step_profit_avg

    print(f"[auto-ε]  t_min={t_min:.1f} min,  t_avg={t_avg:.1f} min  →  "
        f"min_eps_step={min_eps_step}")
    
    # Step 1: Compute Ideal & Nadir points
    _, (g1_I, g2_N), _ = solve_bilevel_model_epsilon_const_MOO_variant(
        instance_path, save_folder, mode="obj_1", verbose=False, verbose2=False)
    
    _, (g1_N, g2_I), _ = solve_bilevel_model_epsilon_const_MOO_variant(
        instance_path, save_folder, mode="obj_2", verbose=False, verbose2=False)
    
    print('')
    print(f"Ideal  point  (flow,max | profit,max): ({g1_I} , {g2_I})")
    print(f"Nadir  point  (flow,min | profit,min): ({g1_N} , {g2_N})")
    print("")

    mode_name          = "eps_obj_2"
    eps_kw             = "profit_lb"
    x_label            = "ε  (Profit (with stockout penalty) lower bound)"
    invert_x           = False

    eps_start, eps_end = g2_N - min_eps_step, g2_I

    
    
    # Step 2: Create epsilon grid using ideal and nadir points and uniform steps or percentage steps
    
    if m_steps is not None:
        eps_grid = np.linspace(eps_start, eps_end, m_steps)
    elif percent_step is not None:
        delta = abs(eps_start - eps_end)
        step  = delta * (percent_step / 100.0)
        eps_grid = np.arange(eps_start, eps_end - step, -step)
    else:
        raise ValueError("Specify m_steps or percent_step")
    
    # dict  ε → (flow, profit, other-stats)
    sol_dict = {}
    summary_rows = []        # collects *all* rows

    def solve_at(eps_val: float):
        if eps in sol_dict:
            return
        kwargs = {eps_kw: eps_val}
        print('')
        print(f"Solving for ε = {eps_val} ({kwargs})")
        print("")
        _, (g1, g2), _ = solve_bilevel_model_epsilon_const_MOO_variant(
                instance_path, save_folder, mode=mode_name,
                verbose=False, **kwargs)
        # ── grab *latest* row from the visualisation helper ───────────────
        df_tmp  = summarize_experiment_solutions(save_folder, show=False)
        row     = df_tmp.iloc[-1].copy()          # last run = just finished
        row["eps"] = eps_val
        row["g1"]  = g1
        row["g2"]  = g2

        summary_rows.append(row)                  # for the final DataFrame
        sol_dict[eps_val] = {"eps": eps, "g1": g1, "g2": g2}  # for the adaptive loop

    # ──────────────────────────
    #  3. first sweep
    # ──────────────────────────
    for eps in eps_grid:
        solve_at(float(eps))
    
    print("\nFirst Sweep done, starting adaptive refinement...\n")

    # ──────────────────────────
    #  4. adaptive refinement
    # ──────────────────────────
    
    '''
    every iteration compares adjacent εs, inserts the midpoint if
    either objective jumps by more than the tolerances, and then the outer
    while changed: loop repeats with the refined set.
    '''
    delta_g2 = min_eps_step
    changed = True
    while changed:
        changed = False
        # sort by ε
        eps_sorted = sorted(sol_dict.keys())
        for left, right in zip(eps_sorted[:-1], eps_sorted[1:]):
            mid_eps = 0.5 * (left + right)
            if (right - left) <= min_eps_step:          # already small gap
                continue
            change_g1 = abs(sol_dict[right]["g1"] - sol_dict[left]["g1"])
            change_g2 = abs(sol_dict[right]["g2"] - sol_dict[left]["g2"])
            if (change_g1 > delta_g1) or (change_g2 > delta_g2):
                print(f" refine [{left:,.2f} … {right:,.2f}]  "
                f"Δg1={change_g1:,.1f}  Δg2={change_g2:,.1f}")
                solve_at(float(mid_eps))
                changed = True        # will trigger another sweep


    # ──────────────────────────
    #  5. tidy up → dataframe
    # ──────────────────────────
    summary_df = pd.DataFrame(summary_rows).sort_values("eps").reset_index(drop=True)
    display(summary_df)                        # or summary_df.to_csv(...)


    # save raw results
    instance_name = os.path.splitext(os.path.basename(instance_path))[0]
    eps_curves_folder = os.path.join(save_folder, "eps_curves")
    os.makedirs(eps_curves_folder, exist_ok=True)
    result_path = os.path.join(eps_curves_folder, f"eps_curve_ideal_nadir_{instance_name}.json")
    summary_df.to_json(result_path, orient="records", indent=2)

    print(f"{len(summary_df)} ε-runs stored ➜ {os.path.basename(result_path)}")

    # Step 4: Plot the pareto front
    plt.figure(figsize=(6,4))
    plt.plot(summary_df[secondary], summary_df["g1"], "ro-")
    if invert_x:
        plt.gca().invert_xaxis()
    plt.xlabel(x_label + ("  → tighter left" if invert_x else "  → tighter right"))
    plt.ylabel("Max primary obj g1  → better up")
    plt.title(f"Pareto Front for g1 and {secondary}\nInstance: {instance_name}")
    plt.tight_layout()
    
    # Save the plot to file
    plot_path = os.path.join(eps_curves_folder, f"pareto_plot_{secondary}_{instance_name}.png")
    plt.savefig(plot_path)
    plt.show()

    pretty_name = "PT-time" if secondary=="g3" else "PT-flow"

    # Step 5: Additional Plots for comparison

    def plot_and_save(x, y, xlabel, ylabel, title, filename, invert_x=invert_x):
        plt.figure(figsize=(6, 4))
        plt.plot(x, y, "o-")
        if invert_x:
            plt.gca().invert_xaxis()
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.title(title)
        plt.tight_layout()
        plt.savefig(os.path.join(eps_curves_folder, filename))
        plt.show()
        plt.close()
    
        # Plot 1: Profit vs secondary
    plot_and_save(summary_df[secondary], summary_df["Profit"],
                  f"{secondary} ({pretty_name})", "Profit",
                  f"Profit vs {secondary}\nInstance: {instance_name}", f"profit_vs_{secondary}_{instance_name}.png")

    # Plot 2: Total Flow (Car) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (Car)"],
                  f"{secondary} ({pretty_name})", "Total Flow (Car)",
                  f"Total Flow (Car) vs {secondary}\nInstance: {instance_name}", f"car_flow_vs_{secondary}_{instance_name}.png")

    # Plot 3: Total Flow (PT Only) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (PT Only)"],
                  f"{secondary} ({pretty_name})", "Total Flow (PT Only)",
                  f"PT Flow vs {secondary}\nInstance: {instance_name}", f"pt_flow_vs_{secondary}_{instance_name}.png")

    # Plot 4: Total Flow (Multimodal) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Total Flow (Multimodal)"],
                  f"{secondary} ({pretty_name})", "Total Flow (Multimodal)",
                  f"Multimodal Flow vs {secondary}\nInstance: {instance_name}", f"multimodal_flow_vs_{secondary}_{instance_name}.png")

    # Plot 5: Avg Bike Price (Multimodal, Flow ≥ 1) vs secondary
    plot_and_save(summary_df[secondary], summary_df["Avg Bike Price (Multimodal, Flow ≥ 1)"],
                  f"{secondary} ({pretty_name})", "Avg Bike Price (Flow ≥ 1)",
                  f"Avg Bike Price vs {secondary}\nInstance: {instance_name}", f"avg_bike_price_vs_{secondary}_{instance_name}.png")

    # Plot 6: Total Flow (Multimodal) vs Total Flow (PT Only)
    plot_and_save(summary_df["Total Flow (PT Only)"], summary_df["Total Flow (Multimodal)"],
                  "Total Flow (PT Only)", "Total Flow (Multimodal)",
                  f"Multimodal vs PT Flow\nInstance: {instance_name}", f"multimodal_vs_pt_flow_{secondary}_{instance_name}.png", invert_x=False)
