import re
import pandas as pd

import matplotlib.pyplot as plt
import matplotlib as mpl
from matplotlib.colors import to_rgba, to_rgb
import colorsys
from matplotlib import colors as mcolors

def _parse_instance_id(id_str: str):
    """
    Extract the numerical 'size' token (9th underscore-separated field)
    and map to size class S / M / L.
    """
    parts = id_str.split("_")
    #if len(parts) < 9:
    #    raise ValueError(f"Bad instance id (needs ≥9 parts): {id_str}")
    n = int(parts[1])
    tag = "S" if n < 2_000 else ("M" if n < 7_000 else ("L" if n < 20_000 else "EL"))
    return tag, n


def _canonicalise_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardise instance names to SMI_<size><rank> and sort S->M->L.
    Works no matter which column carries the instance id, as long
    as its header contains 'Instance Name' (case sensitive).
    """
    df = df.copy()

    name_col = next((c for c in df.columns if "Instance Name" in c), None)
    if name_col:
        df.set_index(name_col, inplace=True)

    tags, nums = zip(*(_parse_instance_id(idx) for idx in df.index))
    df["__tag"] = tags
    df["__num"] = nums

    # stable sort S -> M -> L, then ascending numeric size
    size_order = {"S": 0, "M": 1, "L": 2, "EL": 3}
    df["__tag_ord"] = [size_order[t] for t in df["__tag"]]
    df.sort_values(["__tag_ord", "__num"], inplace=True)

    # ranks inside each size group
    df["__rank"] = df.groupby("__tag").cumcount() + 1
    df.index = [f"SMI_{t}{r}" for t, r in zip(df["__tag"], df["__rank"])]
    df.insert(0, "Instance Name", df.index)   # <‑‑ add this
    return df.drop(columns=["__tag", "__tag_ord", "__rank"])


def _market_share(df: pd.DataFrame) -> pd.DataFrame:
    total = (
        df["Total Flow (Car)"]
        + df["Total Flow (PT Only)"]
        + df.get("Total Flow (Multimodal)", 0)
    )
    return pd.DataFrame(
        {
            "shared": (df["Total Flow (PT Only)"] + df.get("Total Flow (Multimodal)", 0)) / total,
            "car": df["Total Flow (Car)"] / total,
        },
        index=df.index,
    )

def _paired_colors(n_runs: int):
    """
    Generate n_runs visually distinct (light, dark) color pairs.
    We sample from Matplotlib's tab10 cycle, then blend toward white
    for the bar (light) and toward black for the line (dark).
    """
    base_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    # repeat if needed
    base = (base_cycle * ((n_runs // len(base_cycle)) + 1))[:n_runs]

    def lighten(rgb, frac=0.6):
        # mix with white
        r, g, b = mcolors.to_rgb(rgb)
        return (r + (1 - r) * frac, g + (1 - g) * frac, b + (1 - b) * frac)

    def darken(rgb, frac=0.4):
        # mix with black
        r, g, b = mcolors.to_rgb(rgb)
        return (r * (1 - frac), g * (1 - frac), b * (1 - frac))

    return [(lighten(c), darken(c)) for c in base]

def plot_market_share_multi(
    runs: dict,               # {"LL": df1, "HPR": df2, "Bilevel": df3, ...}
    *,
    title: str = "Market-share comparison across scenarios",
    font_family: str = "Times New Roman",
):
    """
    Plot shared-mobility bars + car-share lines for multiple scenarios.

    Parameters
    ----------
    runs : mapping label -> DataFrame
        Each DataFrame must contain columns
          'Total Flow (Car)', 'Total Flow (PT Only)', 'Total Flow (Multimodal)'
        plus either 'Total Demand' *or* enough info to compute it (the three flows).
    title : str
        Figure title.
    font_family : str
        Matplotlib font family to apply (default 'Times New Roman').

    Returns
    -------
    canonicalised_dfs : dict[label -> DataFrame]
        Full, reordered tables (original columns) indexed SMI_<size><rank>,
        restricted to the intersection of instances across all runs (S->M->L order).
    market_share_dfs : dict[label -> DataFrame]
        Two-column tables ('shared','car') aligned to same index (S->M->L) used in plot.
    """
    # ---- harmonise indices -------------------------------------------------
    canonicalised, shares = {}, {}
    for label, raw_df in runs.items():
        can = _canonicalise_index(raw_df)
        canonicalised[label] = can
        shares[label] = _market_share(can)

    # keep only instances common to *all* scenarios
    common_sets = [set(df.index) for df in shares.values()]
    common = set.intersection(*common_sets)
    if not common:
        raise ValueError("No common instances across the supplied DataFrames.")

    # robust S->M->L sort: parse index back (SMI_X#)
    def _sort_key(idx):
        # idx looks like SMI_S12; split on '_' then first char of 2nd token
        part = idx.split("_")[1]  # e.g., S12
        tag = part[0]
        rank = int(part[1:])
        return {"S": 0, "M": 1, "L": 2, "EL":3}[tag], rank

    common = sorted(common, key=_sort_key)

    for label in shares:
        shares[label]        = shares[label].loc[common]
        canonicalised[label] = canonicalised[label].loc[common]

    # ---- plotting ----------------------------------------------------------
    n_inst = len(common)
    n_runs = len(shares)
    bar_w  = 0.6 / n_runs
    x      = range(n_inst)

    # font
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 12))

        color_pairs = _paired_colors(n_runs)  # [(light, dark), ...]

        for k, (label, df) in enumerate(shares.items()):
            bar_c, line_c = color_pairs[k]
            offset = (k - (n_runs - 1) / 2) * bar_w

            # bars – shared-mobility share
            ax.bar(
                [p + offset for p in x],
                df["shared"],
                width=bar_w,
                label=f"Shared-Mobility Share ({label})",
                color=bar_c,
                edgecolor="none",
            )
            # line – car share
            ax.plot(
                x,
                df["car"],
                marker="o",
                linestyle="-",
                label=f"Car Share ({label})",
                color=line_c,
            )
            for i, v in enumerate(df["shared"]):
                ax.text(i + offset, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(list(x))
        ax.yaxis.set_minor_locator(plt.MultipleLocator(0.05))
        ax.grid(axis="y", which="minor", linestyle=":", linewidth=0.5)
        ax.set_xticklabels(common, rotation=45, ha="right", fontfamily=font_family)
        ax.set_ylabel("Share of Total Demand", fontfamily=font_family)
        ax.set_ylim(0.1, 1)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)
        ax.grid(axis="y", linestyle="--", linewidth=0.5)

        # legend with font
        leg = ax.legend(frameon=False, ncol=2, prop={"family": font_family})
        for txt in leg.get_texts():
            txt.set_fontfamily(font_family)

        plt.tight_layout()
        plt.show()

    # -----------------------------------------------------------------------
    return canonicalised, shares

def _market_share_separate(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-instance shares for car, pt-only, and multimodal."""
    mm = df.get("Total Flow (Multimodal)", 0)
    pt = df["Total Flow (PT Only)"]
    car = df["Total Flow (Car)"]
    total = car + pt + mm
    # guard against divide-by-zero
    total = total.replace(0, pd.NA)
    return pd.DataFrame(
        {
            "mm":  mm / total,     # multimodal share
            "pt":  pt / total,     # PT-only share
            "car": car / total,    # car share
        },
        index=df.index,
    )

def plot_market_share_multi_separate(
    runs: dict,
    *,
    title: str = "Market-share comparison across scenarios",
    font_family: str = "Times New Roman",
):
    # ---- harmonise indices -------------------------------------------------
    canonicalised, shares = {}, {}
    for label, raw_df in runs.items():
        can = _canonicalise_index(raw_df)
        canonicalised[label] = can
        shares[label] = _market_share_separate(can)

    common_sets = [set(df.index) for df in shares.values()]
    common = set.intersection(*common_sets)
    if not common:
        raise ValueError("No common instances across the supplied DataFrames.")

    def _sort_key(idx):
        part = idx.split("_")[1]  # e.g., S12, M5, L3, EL1
        
        # Handle multi-character tags like "EL"
        if part.startswith("EL"):
            tag = "EL"
            rank = int(part[2:])  # Skip first 2 chars
        elif part[0] in ["S", "M", "L"]:
            tag = part[0]
            rank = int(part[1:])  # Skip first char
        else:
            # Fallback for unexpected format
            tag = part[0]
            rank = 0
        
        return {"S": 0, "M": 1, "L": 2, "EL": 3}[tag], rank
    
    def _sort_key1(idx):
        part = idx.split("_")[1]  # e.g., S12
        tag, rank = part[0], int(part[1:])
        return {"S": 0, "M": 1, "L": 2, "EL": 3}[tag], rank

    common = sorted(common, key=_sort_key)
    for label in shares:
        shares[label]        = shares[label].loc[common]
        canonicalised[label] = canonicalised[label].loc[common]

    # ---- plotting ----------------------------------------------------------
    n_inst = len(common)
    n_runs = len(shares)
    bar_w  = 0.6 / n_runs
    x      = range(n_inst)

    # helper to derive two related fills for stacked segments
    def _segment_colors(base_rgb):
        from matplotlib import colors as mcolors
        r, g, b = mcolors.to_rgb(base_rgb)
        # mm (bottom) = slightly darker; pt (top) = lighter
        mm_c = (r * 0.85, g * 0.85, b * 0.85)
        pt_c = (r + (1 - r) * 0.35, g + (1 - g) * 0.35, b + (1 - b) * 0.35)
        return mm_c, pt_c

    with plt.rc_context({"font.family": font_family}):
    # --- figure with a dedicated legend column ---
        fig = plt.figure(figsize=(n_inst * 1.6 + 3.5, 8))
        gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 0.4], wspace=0.05)
        ax = fig.add_subplot(gs[0, 0])
        ax_leg = fig.add_subplot(gs[0, 1])
        ax_leg.axis("off")

        color_pairs = _paired_colors(n_runs)  # [(light_bar, dark_line), ...]

        for k, (label, df) in enumerate(shares.items()):
            bar_c, line_c = color_pairs[k]
            mm_c, pt_c = _segment_colors(bar_c)
            offset = (k - (n_runs - 1) / 2) * bar_w

            mm_vals = df["mm"].fillna(0.0)
            pt_vals = df["pt"].fillna(0.0)
            car_vals = df["car"].fillna(0.0)

            # stacked bars
            ax.bar([p + offset for p in x], mm_vals, width=bar_w, label=f"MM Share ({label})",
                color=mm_c, edgecolor="none")
            ax.bar([p + offset for p in x], pt_vals, width=bar_w, bottom=mm_vals,
                label=f"PT Share ({label})", color=pt_c, edgecolor="none")

            # car line
            ax.plot(x, car_vals, marker="o", linestyle="-", label=f"Car Share ({label})", color=line_c)

            # total shared labels
            shared_tot = (mm_vals + pt_vals).values
            for i, v in enumerate(shared_tot):
                ax.text(i + offset, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8)

        # axes cosmetics
        ax.set_xticks(list(x))
        ax.set_xticklabels(common, rotation=45, ha="right", fontfamily=font_family)
        ax.yaxis.set_minor_locator(plt.MultipleLocator(0.05))
        ax.grid(axis="y", which="minor", linestyle=":", linewidth=0.5)
        ax.grid(axis="y", linestyle="--", linewidth=0.5)
        ax.set_ylabel("Share of Total Demand", fontfamily=font_family)
        ax.set_ylim(0.0, 1.0)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)

        # --- build one legend per run, stacked inside ax_leg ---
        ax_leg.remove()
        handles_all, labels_all = ax.get_legend_handles_labels()
        grouped = []
        for lbl in shares.keys():
            for role in (f"MM Share ({lbl})", f"PT Share ({lbl})", f"Car Share ({lbl})"):
                if role in labels_all:
                    idx = labels_all.index(role)
                    grouped.append((handles_all[idx], labels_all[idx]))

        gh, gl = zip(*grouped)

        # Place legend at bottom
        leg = ax.legend(
            gh, gl,
            frameon=False,
            ncol=3,  # one row per scenario
            loc="upper center",
            bbox_to_anchor=(0.5, -0.15),
            prop={"family": font_family, "size": 9},
        )

        for txt in leg.get_texts():
            txt.set_fontfamily(font_family)
        '''
        def get_triplet(lbl):
            keys = [f"MM Share ({lbl})", f"PT Share ({lbl})", f"Car Share ({lbl})"]
            hl = []
            for key in keys:
                if key in labels_all:
                    i = labels_all.index(key)
                    hl.append((handles_all[i], labels_all[i]))
            return zip(*hl) if hl else ([], [])

        # dynamic spacing & font size so it always fits
        row_h = 1.0 / max(n_runs, 1)   # equal vertical slots
        fs = max(8, 11 - (n_runs // 2))
        dy = 0.16
        for j, lbl in enumerate(shares.keys()):
            gh, gl = get_triplet(lbl)
            if not gh:
                continue
            leg = ax_leg.legend(
                gh, gl,
                title=lbl,
                frameon=False,
                ncol=1,
                loc="upper left",
                bbox_to_anchor=(0.0, 1.0 - j * dy),  # stack evenly
                borderaxespad=0.0,
                prop={"family": font_family, "size": fs},
                title_fontsize=fs,
                handlelength=2.0,
                handletextpad=0.6,
                columnspacing=0.8,
            )
            ax_leg.add_artist(leg)
        '''
        #plt.tight_layout()
        plt.show()



    return canonicalised, shares


# NEW FUNCTION: Plot Profit comparison
def plot_profit_multi(
    runs: dict,
    *,
    title: str = "Profit comparison across scenarios",
    font_family: str = "Times New Roman",
):
    """
    Bar plot of profits for each scenario and instance.
    """
    canonicalised = {label: _canonicalise_index(df) for label, df in runs.items()}
    # keep only instances common to all
    all_sets = [set(df.index) for df in canonicalised.values()]
    all_instances = set.union(*all_sets) if all_sets else set()
    if not all_instances:
        raise ValueError("No common instances across the supplied DataFrames.")
    
    # sort as in your main plot with EL support
    def _sort_key(idx):
        part = idx.split("_")[1]
        tag_match = re.match(r'^([SMLEL]+)(\d+)$', part)
        if tag_match:
            tag = tag_match.group(1)
            rank = int(tag_match.group(2))
        else:
            tag = part[0] if part else "S"
            rank = int(part[1:]) if len(part) > 1 else 0
        return {"S": 0, "M": 1, "L": 2, "EL": 3}[tag], rank
    
    all_instances = sorted(all_instances, key=_sort_key)
    for label in canonicalised:
        canonicalised[label] = canonicalised[label].reindex(all_instances)

    n_inst = len(all_instances)
    n_runs = len(runs)
    bar_w = 0.7 / n_runs
    x = range(n_inst)
    
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 6))
        color_pairs = _paired_colors(n_runs)
        
        for k, (label, df) in enumerate(canonicalised.items()):
            bar_c, _ = color_pairs[k]
            offset = (k - (n_runs - 1) / 2) * bar_w
            values = df["Profit"].fillna(0)  # Replace NaN with 0 for plotting
            mask = df["Profit"].notna()  # Track which values are actually present
            ax.bar(
                [p + offset for p in x],
                values,
                width=bar_w,
                label=f"Profit ({label})",
                color=bar_c,
                edgecolor="none",
                alpha = 0.8
            )
            # CHANGE 9: Add value labels only for non-missing data
            for i, (v, is_present) in enumerate(zip(values, mask)):
                if is_present and v > 0:  # Only label if data exists and is positive
                    ax.text(i + offset, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
                elif is_present:  # Handle case where value is 0 but data exists
                    ax.text(i + offset, 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
        
        ax.set_xticks(list(x))
        ax.set_xticklabels(all_instances, rotation=45, ha="right", fontfamily=font_family)
        ax.set_ylabel("Profit", fontfamily=font_family)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)
        ax.legend(frameon=False, ncol=2, prop={"family": font_family})
        plt.tight_layout()
        plt.show()
    
    return canonicalised

# NEW FUNCTION: Plot Profit comparison
def plot_objval_multi(
    runs: dict,
    *,
    title: str = "Profit comparison across scenarios",
    font_family: str = "Times New Roman",
):
    """
    Bar plot of profits for each scenario and instance.
    """
    canonicalised = {label: _canonicalise_index(df) for label, df in runs.items()}
    # keep only instances common to all
    all_sets = [set(df.index) for df in canonicalised.values()]
    all_instances = set.union(*all_sets) if all_sets else set()
    if not all_instances:
        raise ValueError("No common instances across the supplied DataFrames.")
    
    # sort as in your main plot with EL support
    def _sort_key(idx):
        part = idx.split("_")[1]
        tag_match = re.match(r'^([SMLEL]+)(\d+)$', part)
        if tag_match:
            tag = tag_match.group(1)
            rank = int(tag_match.group(2))
        else:
            tag = part[0] if part else "S"
            rank = int(part[1:]) if len(part) > 1 else 0
        return {"S": 0, "M": 1, "L": 2, "EL": 3}[tag], rank
    
    all_instances = sorted(all_instances, key=_sort_key)
    for label in canonicalised:
        canonicalised[label] = canonicalised[label].reindex(all_instances)

    n_inst = len(all_instances)
    n_runs = len(runs)
    bar_w = 0.7 / n_runs
    x = range(n_inst)
    
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 6))
        color_pairs = _paired_colors(n_runs)
        
        for k, (label, df) in enumerate(canonicalised.items()):
            bar_c, _ = color_pairs[k]
            offset = (k - (n_runs - 1) / 2) * bar_w
            values = df["Obj Value"].fillna(0)  # Replace NaN with 0 for plotting
            mask = df["Obj Value"].notna()  # Track which values are actually present
            ax.bar(
                [p + offset for p in x],
                values,
                width=bar_w,
                label=f"Obj Value ({label})",
                color=bar_c,
                edgecolor="none",
                alpha = 0.8
            )
            # CHANGE 9: Add value labels only for non-missing data
            for i, (v, is_present) in enumerate(zip(values, mask)):
                if is_present and v > 0:  # Only label if data exists and is positive
                    ax.text(i + offset, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
                elif is_present:  # Handle case where value is 0 but data exists
                    ax.text(i + offset, 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
        
        ax.set_xticks(list(x))
        ax.set_xticklabels(all_instances, rotation=45, ha="right", fontfamily=font_family)
        ax.set_ylabel("Obj Value", fontfamily=font_family)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)
        ax.legend(frameon=False, ncol=2, prop={"family": font_family})
        plt.tight_layout()
        plt.show()
    
    return canonicalised

# NEW FUNCTION: Plot Profit comparison
def plot_time_multi(
    runs: dict,
    *,
    title: str = "Solution time (s) comparison across scenarios",
    font_family: str = "Times New Roman",
):
    """
    Bar plot of profits for each scenario and instance.
    Plots all available instances from all dataframes, even if some dataframes
    don't have data for certain instances.
    """
    canonicalised = {label: _canonicalise_index(df) for label, df in runs.items()}
    
    # Get ALL instances from all dataframes (union instead of intersection)
    all_sets = [set(df.index) for df in canonicalised.values()]
    all_instances = set.union(*all_sets) if all_sets else set()
    
    if not all_instances:
        raise ValueError("No instances found in any of the supplied DataFrames.")
   
    # sort as in your main plot with EL support
    def _sort_key(idx):
        part = idx.split("_")[1]
        tag_match = re.match(r'^([SMLEL]+)(\d+)$', part)
        if tag_match:
            tag = tag_match.group(1)
            rank = int(tag_match.group(2))
        else:
            tag = part[0] if part else "S"
            rank = int(part[1:]) if len(part) > 1 else 0
        return {"S": 0, "M": 1, "L": 2, "EL": 3}[tag], rank
   
    all_instances = sorted(all_instances, key=_sort_key)
    
    # Reindex all dataframes to include all instances, filling missing values with NaN
    for label in canonicalised:
        canonicalised[label] = canonicalised[label].reindex(all_instances)
    
    n_inst = len(all_instances)
    n_runs = len(runs)
    bar_w = 0.7 / n_runs
    x = range(n_inst)
   
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 6))
        color_pairs = _paired_colors(n_runs)
       
        for k, (label, df) in enumerate(canonicalised.items()):
            bar_c, *_ = color_pairs[k]
            offset = (k - (n_runs - 1) / 2) * bar_w
            
            # Get values, handling NaN values
            values = df["Solution Time (s)"].fillna(0)  # Replace NaN with 0 for plotting
            mask = df["Solution Time (s)"].notna()  # Track which values are actually present
            
            bars = ax.bar(
                [p + offset for p in x],
                values,
                width=bar_w,
                label=f"Solution Time (s) ({label})",
                color=bar_c,
                edgecolor="none",
                alpha=0.8  # Slightly transparent to distinguish missing data
            )
            
            # Add value labels only for non-missing data
            for i, (v, is_present) in enumerate(zip(values, mask)):
                if is_present and v > 0:  # Only label if data exists and is positive
                    ax.text(i + offset, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
                elif is_present:  # Handle case where value is 0 but data exists
                    ax.text(i + offset, 0.01, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
       
        ax.set_xticks(list(x))
        ax.set_xticklabels(all_instances, rotation=45, ha="right", fontfamily=font_family)
        ax.set_ylabel("Solution Time (s)", fontfamily=font_family)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)
        ax.legend(frameon=False, ncol=2, prop={"family": font_family})
        plt.tight_layout()
        plt.show()
   
    return canonicalised

import matplotlib.pyplot as plt

def plot_revenue_multi(runs: dict, *, title: str = "Revenue comparison across scenarios", font_family: str = "Times New Roman"):
    """
    Bar plot of revenues for each scenario and instance.
    """
    canonicalised = {label: _canonicalise_index(df) for label, df in runs.items()}
    # keep only instances common to all
    common_sets = [set(df.index) for df in canonicalised.values()]
    common = set.intersection(*common_sets)
    if not common:
        raise ValueError("No common instances across the supplied DataFrames.")
    # sort as in your main plot
    def _sort_key(idx):
        part = idx.split("_")[1]
        tag = part[0]
        rank = int(part[1:])
        return {"S": 0, "M": 1, "L": 2}[tag], rank
    common = sorted(common, key=_sort_key)
    for label in canonicalised:
        canonicalised[label] = canonicalised[label].loc[common]

    n_inst = len(common)
    n_runs = len(runs)
    bar_w = 0.7 / n_runs
    x = range(n_inst)
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 6))
        color_pairs = _paired_colors(n_runs)
        for k, (label, df) in enumerate(canonicalised.items()):
            bar_c, _ = color_pairs[k]
            offset = (k - (n_runs - 1) / 2) * bar_w
            ax.bar(
                [p + offset for p in x],
                df["Revenue"],
                width=bar_w,
                label=f"Revenue ({label})",
                color=bar_c,
                edgecolor="none",
            )
            for i, v in enumerate(df["Revenue"]):
                ax.text(i + offset, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(list(x))
        ax.set_xticklabels(common, rotation=45, ha="right", fontfamily=font_family)
        ax.set_yscale("log")  # <-- log scale here
        ax.set_ylabel("Revenue", fontfamily=font_family)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)
        ax.legend(frameon=False, ncol=2, prop={"family": font_family})
        plt.tight_layout()
        plt.show()
    return canonicalised

def plot_multimodal_flow_multi(runs: dict, *, title: str = "Multimodal Flow comparison across scenarios", font_family: str = "Times New Roman"):
    """
    Bar plot of Total Flow (Multimodal) for each scenario and instance.
    """
    canonicalised = {label: _canonicalise_index(df) for label, df in runs.items()}
    # keep only instances common to all
    common_sets = [set(df.index) for df in canonicalised.values()]
    common = set.intersection(*common_sets)
    if not common:
        raise ValueError("No common instances across the supplied DataFrames.")
    def _sort_key(idx):
        part = idx.split("_")[1]
        tag = part[0]
        rank = int(part[1:])
        return {"S": 0, "M": 1, "L": 2}[tag], rank
    common = sorted(common, key=_sort_key)
    for label in canonicalised:
        canonicalised[label] = canonicalised[label].loc[common]

    n_inst = len(common)
    n_runs = len(runs)
    bar_w = 0.7 / n_runs
    x = range(n_inst)
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 6))
        color_pairs = _paired_colors(n_runs)
        for k, (label, df) in enumerate(canonicalised.items()):
            bar_c, _ = color_pairs[k]
            offset = (k - (n_runs - 1) / 2) * bar_w
            ax.bar(
                [p + offset for p in x],
                df["Total Flow (Multimodal)"],
                width=bar_w,
                label=f"Multimodal Flow ({label})",
                color=bar_c,
                edgecolor="none",
            )
            for i, v in enumerate(df["Total Flow (Multimodal)"]):
                ax.text(i + offset, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8)
        ax.set_xticks(list(x))
        ax.set_xticklabels(common, rotation=45, ha="right", fontfamily=font_family)
        ax.set_ylabel("Total Flow (Multimodal)", fontfamily=font_family)
        ax.set_title(title, pad=20, fontsize=14, fontweight="bold", fontfamily=font_family)
        ax.legend(frameon=False, ncol=2, prop={"family": font_family})
        plt.tight_layout()
        plt.show()
    return canonicalised


from typing import Tuple, Dict, List
import math
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MultipleLocator  # for minor grid ticks

def sens_plots(
    y_axis: str,
    df: pd.DataFrame,
    *,
    font_family: str = "Times New Roman",
    gap_threshold: float = 4.0,
) -> Tuple[plt.Figure, np.ndarray]:
    """
    Multi-panel sensitivity plots (bar charts).

    • One subplot per instance *size* n (OD-pair count parsed from Instance Name).
    • X-axis: capacity–inventory scenarios (e.g., '20-low_inv', '20-med_inv', '20-high_inv').
    • Bars: grouped by price lower bound (distinct colors) within each scenario.
    • Filters out rows with Gap (%) >= gap_threshold.
    • Unified suptitle and *single* color legend for price lower bounds at the bottom (one row).
    • Top-right of each subplot shows the SMI handle for that n (SMI_S#, SMI_M#, SMI_L#).
    • y_axis ∈ {'Profit', 'Solution Time (s)', 'Market Share'} (case/underscore tolerant).
      - 'Market Share' := (PT Only + Multimodal) / (Car + PT Only + Multimodal)
      - 'Solution Time (s)' is plotted on a log y-scale (shared y disabled for log).

    Returns
    -------
    (fig, axes) : The Matplotlib figure and 2D array of Axes (not shown).

    ------------------------------
    TUNING GUIDE (edit values below)
    ------------------------------
    • BAR / GROUP WIDTH  ->  group_w (closer to 1.0 = tighter bars) and bar_edgewidth / bar_alpha
    • TEXT SIZES         ->  title_fs, panel_title_fs, label_fs, tick_fs, legend_fs
    • OVERALL FIG SIZE   ->  sub_w, sub_h (per-subplot width/height); ncols fixed at 2
    • SPACING BTWN PLOTS ->  wspace, hspace in fig.subplots_adjust(...)
    • SUPER TITLE POS    ->  suptitle_y
    • LEGEND POSITION    ->  legend_y (bbox_to_anchor y) and ncol=len(handles)
    """

    # ---------- TUNING: visual parameters ----------
    # Bars / grouping
    group_w        = 0.92     # group width within each x position (0<group_w<=1). ↑ = wider bars (tighter)
    bar_edgewidth  = 0.2      # outline around bars (0 = none)
    bar_alpha      = 1.0      # bar opacity

    # Font sizes
    title_fs       = 14       # unified title font size
    panel_title_fs = 10       # SMI tag box text size
    label_fs       = 11       # axis label size
    tick_fs        = 9        # tick label size
    legend_fs      = 10       # bottom legend font size

    # Figure sizing (per-subplot) and layout
    ncols          = 2        # fixed two columns as requested
    sub_w          = 0.60     # width multiplier per scenario (final subplot width = max(7, sub_w*len(scenarios)))
    sub_h          = 4.2      # height per subplot (in inches)
    suptitle_y     = 0.93     # super title vertical position (0..1 of figure)
    legend_y       = 0.02     # bottom legend vertical anchor
    wspace         = 0.15     # horizontal space between subplots
    hspace         = 0.23     # vertical space between subplots
    # -----------------------------------------------

    # ---- normalise input table and parse tokens from "Instance Name" ----
    if "Instance Name" not in df.columns:
        if df.index.name and "Instance Name" in df.index.name:
            work = df.reset_index().rename(columns={df.index.name: "Instance Name"})
        else:
            work = df.reset_index().rename(columns={"index": "Instance Name"})
    else:
        work = df.copy()

    def _parse_tokens(s: str):
        # expected: Instance_<n>_fix_euclid_<price_lb>_<cap>_<inv_lo>_<inv_hi>
        parts = str(s).split("_")
        try:
            n = int(parts[1])
        except:
            n = None
        try:
            price_lb = float(parts[4])
        except:
            price_lb = None
        try:
            cap = int(float(parts[5]))
        except:
            cap = None
        try:
            inv_hi = float(parts[7])
        except:
            inv_hi = None

        # inventory band from inv_hi
        if inv_hi is None:
            band = None
        elif inv_hi <= 0.35:
            band = "low_inv"
        elif inv_hi <= 0.75:
            band = "med_inv"
        else:
            band = "high_inv"

        scen = f"{cap}-{band}" if (cap is not None and band is not None) else None
        return n, price_lb, scen

    parsed = work["Instance Name"].apply(_parse_tokens)
    work["__n"] = [p[0] for p in parsed]
    work["__price"] = [p[1] for p in parsed]
    work["__scenario"] = [p[2] for p in parsed]

    # drop badly parsed rows and rows with excessive optimality gap
    if "Gap (%)" in work.columns:
        work = work.loc[
            work["__n"].notna() & work["__price"].notna() & work["__scenario"].notna() & (work["Gap (%)"] < float(gap_threshold))
        ].copy()
    else:
        work = work.loc[
            work["__n"].notna() & work["__price"].notna() & work["__scenario"].notna()
        ].copy()

    # ---- choose metric / build y-values ----
    y_key = y_axis.strip().lower().replace("_", " ")
    if y_key in {"profit"}:
        value_col = "Profit"
    elif y_key in {"solution time", "solution time (s)", "solve time", "time"}:
        value_col = "Solution Time (s)"
    elif y_key in {"market share"}:
        value_col = "__market_share__"
        car = work["Total Flow (Car)"]
        pt = work["Total Flow (PT Only)"]
        mm = work.get("Total Flow (Multimodal)", 0)
        denom = (car + pt + mm).replace(0, pd.NA)
        work[value_col] = (mm) / denom
    else:
        raise ValueError("y_axis must be one of: 'Profit', 'Solution Time (s)', 'Market Share'.")

    work = work.loc[work[value_col].notna()].copy()

    # ---- consistent x-order: capacity asc, then band low→med→high ----
    inv_order = {"low_inv": 0, "med_inv": 1, "high_inv": 2}
    def _scen_key(s: str):
        if not isinstance(s, str) or "-" not in s:
            return (float("inf"), 99)
        cap_str, band = s.split("-", 1)
        try:
            cap_val = int(cap_str)
        except:
            cap_val = float("inf")
        return (cap_val, inv_order.get(band, 99))

    scenarios = sorted(work["__scenario"].unique(), key=_scen_key)

    # ---- price lower bounds (colors) ----
    def _norm_lb(p: float) -> float:
        return round(float(p), 2)  # keep 2dp in case you have 0.25 etc.

    prices_sorted = sorted({_norm_lb(p) for p in work["__price"].unique()})
    base_cycle = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    color_map = {p: base_cycle[i % len(base_cycle)] for i, p in enumerate(prices_sorted)}

    # ---- aggregate by scenario, n, price (mean in case of duplicates) ----
    tidy = (
        work.assign(__price_norm=work["__price"].map(_norm_lb))
            .query("__price_norm in @prices_sorted")
            .groupby(["__scenario", "__n", "__price_norm"], as_index=False)[value_col]
            .mean()
    )

    # ---- SMI handle per n (rank S/M/L groups) ----
    def _tag(n: int) -> str:
        return "S" if n < 2000 else ("M" if n < 7000 else "L")

    unique_n = sorted({int(x) for x in tidy["__n"].unique()})
    order_map = {"S": 0, "M": 1, "L": 2}
    grouped = sorted([(order_map[_tag(n)], n) for n in unique_n])
    ranks = {"S": 0, "M": 0, "L": 0}
    smi_by_n: Dict[int, str] = {}
    for _, n in grouped:
        t = _tag(n)
        ranks[t] += 1
        smi_by_n[n] = f"SMI_{t}{ranks[t]}"

    # ---- global y-limits (for comparable scales across panels) ----
    share_mode = (value_col == "__market_share__")
    if share_mode:
        y_min, y_max = 0.0, 1.0
    else:
        vals = tidy[value_col].replace([np.inf, -np.inf], np.nan).dropna()
        if not vals.empty:
            y_min = float(vals.min())
            y_max = float(vals.max())
            if y_min >= 0:
                y_min = 0.0
            y_max *= 1.05  # small headroom
        else:
            y_min, y_max = 0.0, 1.0

    # ---- layout: 2 columns, rows determined by number of n's ----
    n_panels = len(unique_n)
    nrows = math.ceil(n_panels / ncols)

    # figure sizing
    sub_w_in = max(7.0, sub_w * len(scenarios))   # <- TUNING: overall width per subplot
    sub_h_in = sub_h                               # <- TUNING: overall height per subplot
    fig_w = ncols * sub_w_in
    fig_h = nrows * sub_h_in + 1.4                 # extra for legend

    sharey = False 

    with plt.rc_context({"font.family": font_family}):
        fig, axes = plt.subplots(
            nrows=nrows, ncols=ncols, figsize=(fig_w, fig_h),
            sharex=True, sharey=sharey, squeeze=False
        )

        x = np.arange(len(scenarios))
        n_price = max(1, len(prices_sorted))
        bar_w = group_w / n_price  # <- TUNING: bar width (increase group_w for tighter/wider bars)

        # draw each panel
        for idx, n_val in enumerate(unique_n):
            r, c = divmod(idx, ncols)
            ax = axes[r, c]

            # per-price bars (tight grouping)
            for j, p in enumerate(prices_sorted):
                sub = tidy[(tidy["__n"] == n_val) & (tidy["__price_norm"] == p)]
                y_map = dict(zip(sub["__scenario"], sub[value_col]))
                ys = [y_map.get(sc, np.nan) for sc in scenarios]

                offset = (j - (n_price - 1) / 2) * bar_w
                ax.bar(
                    x + offset, ys, width=bar_w,
                    color=color_map[p], edgecolor="black" if bar_edgewidth > 0 else "none",
                    linewidth=bar_edgewidth, alpha=bar_alpha,
                    label=f"LB = {p:g}"  # labels used for unified legend
                )
            ax.tick_params(axis="x", which="both", labelbottom=True)  # show x tick labels on all subplots
            ax.tick_params(axis="y", which="both", labelleft=True)    # show y tick labels on all subplots
            # axes cosmetics
            ax.set_xticks(x)
            ax.set_xticklabels(scenarios, rotation=30, ha="right", fontsize=tick_fs, fontfamily=font_family)

            if share_mode:
                ax.set_ylim(y_min, y_max)
                ax.yaxis.set_minor_locator(MultipleLocator(0.05))
                ax.grid(axis="y", which="minor", linestyle=":", linewidth=0.5)
            else:
                if value_col == "Solution Time (s)":
                    ax.set_yscale("log")
                else:
                    ax.set_ylim(y_min, y_max)
            ax.grid(axis="y", linestyle="--", linewidth=0.6)

            # X and Y axis labels ON EACH PLOT
            ax.set_xlabel("Dock Capacity and Inventory Scenarios", fontsize=label_fs, fontfamily=font_family)
            
            if share_mode:
                ylabel = "Multi-Modal Market Share of Total Demand"
            elif value_col == "Solution Time (s)":
                ylabel = "Solution Time (s) (log scale)"
            else:
                ylabel=value_col
            ax.set_ylabel(ylabel, fontsize=label_fs, fontfamily=font_family)
            
            
            # --- Per-plot automatic Y limits ---
            auto_ylims = True          # toggle per-plot scaling
            ylim_pad_frac = 0.08       # headroom around data (fraction of range)
            force_zero_baseline = False  # set True to force ymin=0
            # dfg = data for THIS subplot (size n == n_val)
            dfg = tidy.loc[tidy["__n"] == n_val, [value_col]].dropna()
            if auto_ylims:
                # dfg: the DataFrame slice for THIS subplot (size n)
                vals = dfg[value_col].dropna().to_numpy()
                if vals.size:
                    vmin = float(np.nanmin(vals))
                    vmax = float(np.nanmax(vals))
                    if value_col == "Solution Time (s)":
                        vmin = max(vmin, np.finfo(float).tiny)   # avoid 0 on log scale
                        ymin = vmin / (1.0 + ylim_pad_frac)
                        ymax = vmax * (1.0 + ylim_pad_frac)
                    else:
                        rng = vmax - vmin
                        if rng <= 0:
                            rng = abs(vmax) if vmax != 0 else 1.0
                        pad = ylim_pad_frac * rng
                        ymin = 0.0 if force_zero_baseline else (vmin - pad)
                        ymax = vmax + pad
                        if value_col == "__market_share__":
                            ymin = max(0.0, ymin)
                            ymax = min(1.0, ymax)
                    if np.isfinite(ymin) and np.isfinite(ymax) and ymin < ymax:
                        ax.set_ylim(ymin, ymax)


            # tick sizes
            ax.tick_params(axis="y", labelsize=tick_fs)

            # SMI label at top-right of each subplot
            ax.text(
                0.98, 0.96, smi_by_n[int(n_val)],
                transform=ax.transAxes,
                ha="right", va="top",
                fontsize=panel_title_fs, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.6, edgecolor="none")
            )

        # hide any empty axes (when panels are odd)
        for k in range(n_panels, nrows * ncols):
            r, c = divmod(k, ncols)
            axes[r, c].axis("off")

        # unified title

        if y_axis == "Market Share":
            title = "Multi-Modal Market Share"
        else:
            title = y_axis
        fig.suptitle(
            f"Sensitivity Scenarios and Results for {title} in Geneva Instances",
            fontsize=title_fs, fontweight="bold", y=suptitle_y, fontfamily=font_family
        )

        # unified legend (colors for price lb) at bottom in one row
        handles = [Patch(facecolor=color_map[p], edgecolor="none", label=f"Price LB = {p:g}") for p in prices_sorted]
        fig.legend(
            handles=handles,
            loc="lower center",
            ncol=len(handles),
            frameon=False,
            bbox_to_anchor=(0.5, legend_y),
            prop={"family": font_family, "size": legend_fs},
        )

        # layout tweaks: space for suptitle and legend
        fig.subplots_adjust(top=0.90, bottom=0.12, wspace=wspace, hspace=hspace)  # <- TUNING: wspace & hspace

    return fig, axes
