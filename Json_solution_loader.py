import json
import pandas as pd

# Load a JSON solution file into a DataFrame
def load_solution_json(solution_path):
    with open(solution_path, "r") as f:
        data = json.load(f)
    df = pd.DataFrame(data["instances"])  # Extract instances list into a DataFrame
    return df