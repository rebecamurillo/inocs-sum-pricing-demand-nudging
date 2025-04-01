import ipywidgets as widgets
from IPython.display import display
from Vis_Codes.visualization_of_the_solution import visualize_bilevel_solution

def display_bilevel_solution_with_ui(cluster_df, solution_json_path, preprocessing_data_path):
    """
    Displays an interactive solution visualization UI.
    
    This function creates input widgets for the origin and destination hub IDs and then uses
    the visualize_solution() function (which should be defined elsewhere) to display the
    corresponding folium map. The UI and map are updated interactively when the user changes
    the input values.
    
    Parameters:
      cluster_df: GeoDataFrame of hubs (clusters) with columns 'hub_id' and 'geometry' (EPSG:4326).
      solution_json_path: Path to the solution JSON file.
      preprocessing_data_path: Path to the network (preprocessing) JSON file.
    
    Returns:
      None (displays the interactive UI and map in the notebook).
    """
    def update_map(origin, destination):
        # Call your visualization function with the selected origin and destination.
        m = visualize_bilevel_solution(cluster_df, solution_json_path, preprocessing_data_path, origin, destination, search=True)
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
