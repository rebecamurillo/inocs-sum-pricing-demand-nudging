# Re-import required packages after kernel reset
import matplotlib.pyplot as plt
import pandas as pd
from pandas.plotting import parallel_coordinates
from mpl_toolkits.mplot3d import Axes3D

def extract_solution_metrics(solution, arcs_pt_bike, arcs_pt_only, bike_time, W):
    """
    Extracts the secondary metrics from a solution dictionary for Pareto analysis.
    Removes q_a1 from metrics.
    """
    q_all = 0.0
    pt_time_a2 = 0.0
    revenue_a1 = 0.0

    for (o, d) in W:
        od_key = f"{o}_{d}"

        for arc in arcs_pt_bike.get(od_key, []):
            arc_id = arc["arc_id"]
            q_val = solution.get(f"q_{o}_{d}_{arc_id}", 0.0)
            p_val = solution.get(f"p_{o}_{d}_{arc_id}", 0.0)
            tau = bike_time[(o, d, arc_id)]
            q_all += q_val
            revenue_a1 += p_val * tau * q_val

        for arc in arcs_pt_only.get(od_key, []):
            arc_id = arc["arc_id"]
            q_val = solution.get(f"q_{o}_{d}_{arc_id}", 0.0)
            q_all += q_val
            pt_time_a2 += arc["pt_time"] * q_val

    return [q_all, -pt_time_a2, revenue_a1]

def is_dominated(candidate, others):
    for other in others:
        if all(o >= c for o, c in zip(other, candidate)) and any(o > c for o, c in zip(other, candidate)):
            return True
    return False

def plot_parallel(metrics, pareto_indices):
    df = pd.DataFrame(metrics, columns=["q_all", "-pt_time", "revenue_a1"])
    df["Label"] = ["Pareto" if i in pareto_indices else "Other" for i in range(len(metrics))]
    plt.figure(figsize=(10, 6))
    parallel_coordinates(df, class_column="Label", color=("#999999", "#FF0000"))
    plt.title("Parallel Coordinates Plot")
    plt.grid(True)
    plt.show()

def plot_3d_pareto(metrics, pareto_indices):
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    x = [m[0] for m in metrics]
    y = [-m[1] for m in metrics]
    z = [m[2] for m in metrics]

    ax.scatter(x, y, z, c='gray', label='All Solutions')
    ax.scatter([x[i] for i in pareto_indices],
               [y[i] for i in pareto_indices],
               [z[i] for i in pareto_indices],
               c='red', label='Pareto Front')
    ax.set_xlabel("Total Flow")
    ax.set_ylabel("Total PT Time")
    ax.set_zlabel("Revenue (A1)")
    ax.set_title("3D Pareto Front")
    ax.legend()
    plt.show()

def compute_pareto_front(solutions, arcs_pt_bike, arcs_pt_only, bike_time, W, plot_2d=True, plot_3d=True):
    metrics = [extract_solution_metrics(sol, arcs_pt_bike, arcs_pt_only, bike_time, W) for sol in solutions]
    pareto_indices = []

    for i, candidate in enumerate(metrics):
        if not is_dominated(candidate, [m for j, m in enumerate(metrics) if j != i]):
            pareto_indices.append(i)

    if plot_2d:
        plot_parallel(metrics, pareto_indices)

    if plot_3d:
        plot_3d_pareto(metrics, pareto_indices)

    return pareto_indices
