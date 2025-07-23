import json
import pandas as pd
import random
from pathlib import Path

def transform_bike_data(json_path: str, df_path: str, base_cap_value: int):
    # Set random seed for reproducibility
    random.seed(42)

    # Load the JSON file
    with open(json_path, 'r') as f:
        original_data = json.load(f)
    print(f"Loaded JSON from {json_path}")
    # Load the DataFrame from pickle
    df = pd.read_pickle(df_path)

    # Count PT stations per hub
    df["number_of_pt_stations"] = df["pt_stations"].apply(lambda x: len(x))

    # Identify high-density PT hubs (threshold >= 5)
    high_density_hubs = set(df[df["number_of_pt_stations"] >= 4]["hub_id"])

    # Explode the bike_stations column to count stations per hub_id
    df_exploded = df.explode("bike_stations")
    station_counts = df_exploded.groupby("hub_id")["bike_stations"].count().rename("number_of_stations")

    # Merge counts back to the original df
    df = df.merge(station_counts, on="hub_id")

    # Add capacity column
    cap_col = f"base_capacity_{base_cap_value}"
    df[cap_col] = df["number_of_stations"] * base_cap_value

    # Modify demand if needed
    for entry in original_data.get("demand", []):
        origin = entry.get("origin")
        destination = entry.get("destination")

        if origin in high_density_hubs:
            total_out_demand = sum(e["demand"] for e in original_data["demand"] if e["origin"] == origin)
            if total_out_demand < 200:
                entry["demand"] *= 1.5

        if destination in high_density_hubs:
            total_in_demand = sum(e["demand"] for e in original_data["demand"] if e["destination"] == destination)
            if total_in_demand < 200:
                entry["demand"] *= 1.5

    # Define inventory scenarios
    inventory_scenarios = {
        "low": (0.0, 0.3),
        "high": (0.7, 1.0),
        "random": (0.0, 1.0),
    }

    output_files = []

    for scenario_name, (min_ratio, max_ratio) in inventory_scenarios.items():
        # Deep copy the data to avoid overwriting
        data = json.loads(json.dumps(original_data))

        # Update station_capacity and number_of_dock_stations only for existing station_list
        station_list = data["bike_stations"].get("station_list", [])
        updated_station_capacity = {}
        updated_station_inventory = {}
        updated_number_of_dock_stations = {}

        for station_id in station_list:
            row = df[df["hub_id"] == station_id]
            if not row.empty:
                cap = int(row[cap_col].values[0])
                updated_station_capacity[str(station_id)] = cap
                updated_number_of_dock_stations[str(station_id)] = int(row["number_of_stations"].values[0])
                updated_station_inventory[str(station_id)] = int(random.uniform(min_ratio, max_ratio) * cap)

        data["bike_stations"]["station_capacity"] = updated_station_capacity

        if "number_of_dock_stations" not in data["bike_stations"]:
            data["bike_stations"]["number_of_dock_stations"] = updated_number_of_dock_stations

        data["bike_stations"]["station_inventory"] = updated_station_inventory

        # Save modified JSON
        updated_json_path = Path(json_path).with_name(
            f"updated_basecap_{base_cap_value}_{scenario_name}_" + Path(json_path).name
        )
        with open(updated_json_path, 'w') as f:
            json.dump(data, f, indent=4)

        output_files.append(str(updated_json_path))

    # Save updated DataFrame as pickle
    updated_df_path = Path(df_path).with_name(f"updated_basecap_{base_cap_value}_" + Path(df_path).stem + ".pkl")
    df.to_pickle(updated_df_path)

    return output_files, str(updated_df_path)

base_value  = 20

# Example usage: for path in paths:
                    #transform_bike_data(path, pickle_path, base_value)
