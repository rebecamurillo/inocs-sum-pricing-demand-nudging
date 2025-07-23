#Bilevel_Solution_Visualization.py

import os
import pickle
import ipywidgets as widgets
from IPython.display import display, clear_output
import geopandas as gpd
from visualize_solutions.Vis_Codes.visualize_bilevel_solution_with_ui import display_bilevel_solution_with_ui
from visualize_solutions.Vis_Codes.summarizer import summarize_experiment_solutions
from visualize_solutions.Vis_Codes.summarizer_pre_lexi import summarize_pre_lexicographic_experiment_solutions
from visualize_solutions.Vis_Codes.summarizer_multi_obj import summarise_multiobj_solutions

class Bilevel_Solution_Visualizer:
    def __init__(self, 
                pickle_path=None,
                network_path=None,
                solution_path=None,
                nodes_geo_path=None,        # NEW
                nodes_poly_path=None,       # NEW
                pickle_folder=None,
                network_folder=None,
                solution_folder=None,
                nodes_geo_folder=None,      # NEW
                nodes_poly_folder=None):    # NEW
        def _is_valid_file(path, ext):
            return path and os.path.isfile(path) and path.endswith(ext)
        
        #for given paths, visualize
        self.pickle_path = pickle_path if _is_valid_file(pickle_path, ".pkl") else None
        self.network_path = network_path if _is_valid_file(network_path, ".json") else None
        self.solution_path = solution_path if _is_valid_file(solution_path, ".json") else None
        self.nodes_geo_path = nodes_geo_path if _is_valid_file(nodes_geo_path, ".pkl") else None
        self.nodes_poly_path = nodes_poly_path if _is_valid_file(nodes_poly_path, ".pkl") else None
        #folders for dropdown menu
        self.pickle_folder = pickle_folder if os.path.isdir(pickle_folder or '') else None
        self.network_folder = network_folder if os.path.isdir(network_folder or '') else None
        self.solution_folder = solution_folder if os.path.isdir(solution_folder or '') else None
        self.nodes_geo_folder = nodes_geo_folder if os.path.isdir(nodes_geo_folder or '') else None
        self.nodes_poly_folder = nodes_poly_folder if os.path.isdir(nodes_poly_folder or '') else None
        
        self.use_dropdown_ui = not (self.pickle_path and self.network_path and self.nodes_poly_path and self.nodes_geo_path and self.solution_path)

        if self.use_dropdown_ui:
            self._gather_files()
            self._build_widgets()
            self._render_ui()
        else:
            self._visualize_direct()

    def _gather_files(self):

        self.pickle_files = []
        self.network_files =[]
        self.solution_files = []
        self.nodes_geo_files  = []
        self.nodes_poly_files = []

        if self.pickle_folder:
            self.pickle_files = [f for f in os.listdir(self.pickle_folder) if f.endswith('.pkl')]
            self.nodes_geo_files = [f for f in os.listdir(self.pickle_folder) if f.endswith('.pkl')]
            self.nodes_poly_files = [f for f in os.listdir(self.pickle_folder) if f.endswith('.pkl')]
        if self.network_folder:
            self.network_files = [f for f in os.listdir(self.network_folder) if f.endswith('.json')]
        if self.solution_folder:
            self.solution_files = [f for f in os.listdir(self.solution_folder) if f.endswith('.json') and "solution" in f.lower()]

    def _build_widgets(self):
        self.pickle_files_dropdown = widgets.Dropdown(options = self.pickle_files, description='Hubs Data Pickle File:')
        self.nodes_geo_files_dropdown = widgets.Dropdown(options = self.nodes_geo_files, description='Nodes Geo Data Pickle File:')
        self.nodes_poly_files_dropdown = widgets.Dropdown(options = self.nodes_poly_files, description='Nodes Poly Data Pickle File:')
        self.network_files_dropdown = widgets.Dropdown(options = self.network_files, description='Network Data Json File:')
        self.solution_files_dropdown = widgets.Dropdown(options = self.solution_files, description='Solution Json File:')
        self.visualize_button = widgets.Button(description='Visualize')
        self.map_output = widgets.Output()
        self.visualize_button.on_click(self._on_visualize_clicked)

    #Visualize if path to a folder is given

    def _on_visualize_clicked(self, b):
        with self.map_output:
            clear_output(wait = True)
            try:
                pickle_path = os.path.join(self.pickle_folder, self.pickle_files_dropdown.value)
                network_path = os.path.join(self.network_folder, self.network_files_dropdown.value)
                solution_path = os.path.join(self.solution_folder, self.solution_files_dropdown.value)
                nodes_geo_path = os.path.join(self.pickle_folder, self.nodes_geo_files_dropdown.value)
                nodes_poly_path = os.path.join(self.pickle_folder, self.nodes_poly_files_dropdown.value)
                self._visualize(pickle_path, network_path, nodes_geo_path, nodes_poly_path, solution_path)

            except Exception as e:
                print(f"Error: {e}")

    #Visualize if only path to files are given

    def _visualize_direct(self):
        self.map_output = widgets.Output()
        display(self.map_output)
        with self.map_output:
            clear_output(wait=True)
            try:
                self._visualize(self.pickle_path, self.network_path, self.nodes_geo_path, self.nodes_poly_path, self.solution_path)
           
            except Exception as e:
                print(f"Error (direct visualization): {e}")

    #Call visualization function

    def _visualize(self, pickle_path, network_path, nodes_geo_path, nodes_poly_path, solution_path):
        with open(pickle_path, 'rb') as f:
            hub_df = pickle.load(f)
        with open(nodes_geo_path, 'rb') as f:
            stops_gdf = pickle.load(f)
        with open(nodes_poly_path, 'rb') as f:
            polys_gdf = pickle.load(f)

        hub_df = gpd.GeoDataFrame(hub_df, geometry='geometry', crs='EPSG:3857')
        m = display_bilevel_solution_with_ui(hub_df, network_path, nodes_geo_path=stops_gdf, nodes_poly_path=polys_gdf, solution_json_path=solution_path)

        display(m)


    def _render_ui(self):
        ui = widgets.VBox([
            self.network_files_dropdown,
            self.solution_files_dropdown,
            self.pickle_files_dropdown,
            self.nodes_geo_files_dropdown,
            self.nodes_poly_files_dropdown,
            self.visualize_button
        ])
        display(ui, self.map_output)
    
    def summarize(self):
        folder = self.solution_folder or os.path.dirname(self.solution_path)
        return summarize_experiment_solutions(folder)
    
    def summarize_pre_lexi(self):
        folder = self.solution_folder or os.path.dirname(self.solution_path)
        return summarize_pre_lexicographic_experiment_solutions(folder)
    
    def summarize_multi_obj(self):
        folder = self.solution_folder or os.path.dirname(self.solution_path)
        return summarise_multiobj_solutions(folder)