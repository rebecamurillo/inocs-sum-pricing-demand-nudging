import ipywidgets as widgets
from IPython.display import display
from .visualization_of_the_solution import visualize_bilevel_solution
import json

def display_bilevel_solution_with_ui(cluster_df, network_data_path, solution_json_path):
    """
    Displays an interactive solution visualization UI.
    
    This function creates input widgets for the origin and destination hub IDs and uses
    the visualize_bilevel_solution() function to display the corresponding folium map.
    In addition, it reads the demand information from the network JSON file and
    prints the demand value for the chosen OD pair.
    
    Parameters:
      cluster_df: GeoDataFrame of hubs (clusters) with columns 'hub_id' and 'geometry' (EPSG:4326).
      solution_json_path: Path to the solution JSON file.
      network_data_path: Path to the network (network) JSON file, which contains OD pair demand.
    
    Returns:
      None (displays the interactive UI and map in the notebook).
    """
    def update_map(origin, destination):
        # Read the OD pair demand from the network data.
        with open(network_data_path, "r") as f:
            preproc_data = json.load(f)
        od_pairs = preproc_data.get("OD_pairs", [])
        demand_value = None
        for od in od_pairs:
            if od.get("origin") == origin and od.get("destination") == destination:
                demand_value = od.get("demand")
                break
        if demand_value is not None:
            print(f"Demand for OD pair {origin} -> {destination}: {demand_value}")
        else:
            print(f"No demand info found for OD pair {origin} -> {destination}")
        
        # Call the visualization function.
        m = visualize_bilevel_solution(cluster_df, network_data_path, solution_json_path, origin, destination, search=True)
        display(m)
    
    # Create input widgets for origin and destination.
    origin_widget = widgets.IntText(value=4, description='Origin:')
    destination_widget = widgets.IntText(value=5, description='Destination:')
    
    # Arrange widgets and create interactive output.
    ui = widgets.HBox([origin_widget, destination_widget])
    out = widgets.interactive_output(update_map, {'origin': origin_widget, 'destination': destination_widget})
    
    # Display the UI and the interactive map.
    display(ui, out)


# Example usage:
# display_solution_with_ui(cluster_df, "solution.json", "network.json")
