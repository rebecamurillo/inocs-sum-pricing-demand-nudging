import pickle
import pandas as pd

def build_bike_od_counts(matched_bike_trips_df: pd.DataFrame,
                         hub_df: pd.DataFrame,
                         pickle_path: str | None = None,
                         *,
                         season: str | None = None,
                         time_slot: str | None = None,
                         verbose: bool = True) -> pd.DataFrame:
    """
    Construct a hub‑to‑hub bicycle OD table from raw trip rows and
    (optionally) persist it as a pickle file.

    Parameters
    ----------
    bike_trips_df : DataFrame
        Long‑format trips table.  Required columns:
        ['trip_id', 'point_type', 'matched bike station name']
        Optionally includes 'season' and 'time_slot'.
    hub_df : DataFrame / GeoDataFrame
        Must contain columns:
        • 'hub_id'          – integer or string identifier
        • 'bike_stations'   – list of station names belonging to the hub
    pickle_path : str or None, default None
        Where to `pickle.dump()` the resulting DataFrame.
        If None, nothing is written to disk.
    season : str or None
        If given, keep only rows where `season == season`.
    time_slot : str or None
        If given, keep only rows where `time_slot == time_slot`.
    verbose : bool
        Print basic row counts.

    Returns
    -------
    od_counts : DataFrame
        Columns: ['origin_hub', 'destination_hub', 'trip_count'].
    """

    df = matched_bike_trips_df.copy()

    # -- optional filters ----------------------------------------------------
    if season is not None:
        df = df[df["season"] == season]
    if time_slot is not None:
        df = df[df["time_slot"] == time_slot]

    if verbose:
        print(f"Rows after filtering: {len(df):,}")

    # -- pivot long → wide ---------------------------------------------------
    wide = (
        df.pivot(index="trip_id",
                 columns="point_type",
                 values="matched bike station name")
          .reset_index()
    )

    # -- map station → hub ---------------------------------------------------
    station_to_hub = {
        station: row["hub_id"]
        for _, row in hub_df.iterrows()
        for station in row["bike_stations"]
    }

    wide["origin_hub"]      = wide["origin"].map(station_to_hub)
    wide["destination_hub"] = wide["destination"].map(station_to_hub)

    before_drop = len(wide)
    wide = wide.dropna(subset=["origin_hub", "destination_hub"])
    if verbose:
        dropped = before_drop - len(wide)
        print(f"Dropped {dropped:,} trips with unmapped stations")

    # -- aggregate -----------------------------------------------------------
    od_counts = (
        wide.groupby(["origin_hub", "destination_hub"])
            .size()
            .reset_index(name="trip_count")
            .astype({"origin_hub": int, "destination_hub": int, "trip_count": int})
    )

    if verbose:
        print(f"Unique OD pairs: {len(od_counts):,}")

    # -- optional persistence ------------------------------------------------
    if pickle_path:
        pickle.dump(od_counts, open(pickle_path, "wb"))
        if verbose:
            print(f"Saved OD table → {pickle_path}")

    return od_counts
