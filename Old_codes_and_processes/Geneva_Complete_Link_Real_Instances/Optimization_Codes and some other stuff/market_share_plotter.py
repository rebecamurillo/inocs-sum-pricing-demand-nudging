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
    if len(parts) < 9:
        raise ValueError(f"Bad instance id (needs ≥9 parts): {id_str}")
    n = int(parts[8])
    tag = "S" if n < 2_000 else ("M" if n < 7_000 else "L")
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
    size_order = {"S": 0, "M": 1, "L": 2}
    df["__tag_ord"] = [size_order[t] for t in df["__tag"]]
    df.sort_values(["__tag_ord", "__num"], inplace=True)

    # ranks inside each size group
    df["__rank"] = df.groupby("__tag").cumcount() + 1
    df.index = [f"SMI_{t}{r}" for t, r in zip(df["__tag"], df["__rank"])]
    df.index.name = "Instance Name"
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
        return {"S": 0, "M": 1, "L": 2}[tag], rank

    common = sorted(common, key=_sort_key)

    for label in shares:
        shares[label]        = shares[label].loc[common]
        canonicalised[label] = canonicalised[label].loc[common]

    # ---- plotting ----------------------------------------------------------
    n_inst = len(common)
    n_runs = len(shares)
    bar_w  = 0.8 / n_runs
    x      = range(n_inst)

    # font
    with plt.rc_context({"font.family": font_family}):
        fig, ax = plt.subplots(figsize=(n_inst * 1.6, 6))

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

        ax.set_xticks(list(x))
        ax.set_xticklabels(common, rotation=45, ha="right", fontfamily=font_family)
        ax.set_ylabel("Share of Total Demand", fontfamily=font_family)
        ax.set_ylim(0, 1)
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