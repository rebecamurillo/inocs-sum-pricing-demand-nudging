<<<<<<< HEAD
import json, os, numpy as np
import matplotlib.pyplot as plt
from Codes.CPPMTO_optimizer1_epsilon_const_MOO import solve_bilevel_model_epsilon_const_MOO
from visualize_solutions.Bilevel_Solution_Visualization import summarize_experiment_solutions
from IPython.display import display
import pandas as pd

def run_epsilon_constraint_analysis(instance_path, save_folder,secondary="g3", m_steps=None, percent_step= None):
    os.makedirs(save_folder, exist_ok=True)

    # Step 1: Compute Ideal & Nadir points
    _, (g1_I, g2_N, g3_N), _ = solve_bilevel_model_epsilon_const_MOO(
        instance_path, save_folder, mode="g1", verbose=False, verbose2=False)
    
    if secondary == "g3":
        _, (g1_N, _, g3_I), _ = solve_bilevel_model_epsilon_const_MOO(
        instance_path, save_folder, mode="g3", verbose=False, verbose2=False)
    
        print('')
        print(f"Ideal  point  (g1,max | g3,min): ({g1_I} , {g3_I})")
        print(f"Nadir  point  (g1,min | g3,max): ({g1_N} , {g3_N})")
        print("")

        mode_name          = "eps_g3"
        eps_kw             = "time_ub"
        x_label            = "ε  (PT-time upper bound)"
        invert_x           = True

        eps_start, eps_end = g3_N - 1, g3_I
    
    elif secondary == "g2":
        _, (g1_N, g2_I, _), _ = solve_bilevel_model_epsilon_const_MOO(
        instance_path, save_folder, mode="g2", verbose=False, verbose2=False)
        print('')
        print(f"Ideal  point  (g1,max | g2,max): ({g1_I} , {g2_I})")
        print(f"Nadir  point  (g1,min | g2,min): ({g1_N} , {g2_N})")
        print("")


        mode_name          = "eps_g2"
        eps_kw             = "pt_flow_lb"
        x_label            = "ε  (PT-flow lower bound)"
        invert_x           = False

        eps_start, eps_end = g2_N-1, g2_I
            
    else:
        raise ValueError("secondary must be 'g2' or 'g3'")
    
    
    # Step 2: Create epsilon grid using ideal and nadir points and uniform steps or percentage steps
    
    if m_steps is not None:
        eps_grid = np.linspace(eps_start, eps_end, m_steps)
    elif percent_step is not None:
        delta = abs(eps_start - eps_end)
        step  = delta * (percent_step / 100.0)
        eps_grid = np.arange(eps_start, eps_end - step, -step)
    else:
        raise ValueError("Specify m_steps or percent_step")
    
    summary_data = []
    results = []

    # Step 3: Solve for each ε
    for eps in eps_grid:
        solve_kwargs = {eps_kw: eps}
        _, (g1, g2, g3), _ = solve_bilevel_model_epsilon_const_MOO(
            instance_path, save_folder,
            mode=mode_name,
            verbose=False, **solve_kwargs)
        
        df = summarize_experiment_solutions(save_folder, show=False)

        latest_row = df.iloc[-1].copy()
        latest_row["eps"] = eps #attach current epsilon value
        latest_row[secondary] = g2
        latest_row["g3"] = g3
        summary_data.append(latest_row)


        results.append({"eps": eps, "g1": g1, "g2": g2, "g3": g3})

    summary_df = pd.DataFrame(summary_data)
    display(summary_df)

    # Step 4: Save results
    instance_name = os.path.splitext(os.path.basename(instance_path))[0]
    eps_curves_folder = os.path.join(save_folder, "eps_curves")
    os.makedirs(eps_curves_folder, exist_ok=True)
    result_path = os.path.join(eps_curves_folder, f"eps_curve_ideal_nadir_{instance_name}.json")
    
    with open(result_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"{len(results)} ε-runs stored ➜ {os.path.basename(result_path)}")

    # Step 4: Plot the pareto front
    plt.figure(figsize=(6,4))
    plt.plot([r[secondary] for r in results],
             [r["g1"] for r in results],
             "ro-")
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
=======
import json, os, numpy as np
import matplotlib.pyplot as plt
from Codes.CPPMTO_optimizer1_epsilon_const_MOO import solve_bilevel_model_epsilon_const_MOO
from visualize_solutions.Bilevel_Solution_Visualization import summarize_experiment_solutions
from IPython.display import display
import pandas as pd

def run_epsilon_constraint_analysis(instance_path, save_folder,secondary="g3", m_steps=None, percent_step= None):
    os.makedirs(save_folder, exist_ok=True)

    # Step 1: Compute Ideal & Nadir points
    _, (g1_I, g2_N, g3_N), _ = solve_bilevel_model_epsilon_const_MOO(
        instance_path, save_folder, mode="g1", verbose=False, verbose2=False)
    
    if secondary == "g3":
        _, (g1_N, _, g3_I), _ = solve_bilevel_model_epsilon_const_MOO(
        instance_path, save_folder, mode="g3", verbose=False, verbose2=False)
    
        print('')
        print(f"Ideal  point  (g1,max | g3,min): ({g1_I} , {g3_I})")
        print(f"Nadir  point  (g1,min | g3,max): ({g1_N} , {g3_N})")
        print("")

        mode_name          = "eps_g3"
        eps_kw             = "time_ub"
        x_label            = "ε  (PT-time upper bound)"
        invert_x           = True

        eps_start, eps_end = g3_N - 1, g3_I
    
    elif secondary == "g2":
        _, (g1_N, g2_I, _), _ = solve_bilevel_model_epsilon_const_MOO(
        instance_path, save_folder, mode="g2", verbose=False, verbose2=False)
        print('')
        print(f"Ideal  point  (g1,max | g2,max): ({g1_I} , {g2_I})")
        print(f"Nadir  point  (g1,min | g2,min): ({g1_N} , {g2_N})")
        print("")


        mode_name          = "eps_g2"
        eps_kw             = "pt_flow_lb"
        x_label            = "ε  (PT-flow lower bound)"
        invert_x           = False

        eps_start, eps_end = g2_N-1, g2_I
            
    else:
        raise ValueError("secondary must be 'g2' or 'g3'")
    
    
    # Step 2: Create epsilon grid using ideal and nadir points and uniform steps or percentage steps
    
    if m_steps is not None:
        eps_grid = np.linspace(eps_start, eps_end, m_steps)
    elif percent_step is not None:
        delta = abs(eps_start - eps_end)
        step  = delta * (percent_step / 100.0)
        eps_grid = np.arange(eps_start, eps_end - step, -step)
    else:
        raise ValueError("Specify m_steps or percent_step")
    
    summary_data = []
    results = []

    # Step 3: Solve for each ε
    for eps in eps_grid:
        solve_kwargs = {eps_kw: eps}
        _, (g1, g2, g3), _ = solve_bilevel_model_epsilon_const_MOO(
            instance_path, save_folder,
            mode=mode_name,
            verbose=False, **solve_kwargs)
        
        df = summarize_experiment_solutions(save_folder, show=False)

        latest_row = df.iloc[-1].copy()
        latest_row["eps"] = eps #attach current epsilon value
        latest_row[secondary] = g2
        latest_row["g3"] = g3
        summary_data.append(latest_row)


        results.append({"eps": eps, "g1": g1, "g2": g2, "g3": g3})

    summary_df = pd.DataFrame(summary_data)
    display(summary_df)

    # Step 4: Save results
    instance_name = os.path.splitext(os.path.basename(instance_path))[0]
    eps_curves_folder = os.path.join(save_folder, "eps_curves")
    os.makedirs(eps_curves_folder, exist_ok=True)
    result_path = os.path.join(eps_curves_folder, f"eps_curve_ideal_nadir_{instance_name}.json")
    
    with open(result_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"{len(results)} ε-runs stored ➜ {os.path.basename(result_path)}")

    # Step 4: Plot the pareto front
    plt.figure(figsize=(6,4))
    plt.plot([r[secondary] for r in results],
             [r["g1"] for r in results],
             "ro-")
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
>>>>>>> 1655082a5d8beda6aae5106606ff18724c579722
