# save_solution_files_safely.py
# Add this function at the top of your file:
import os

def save_solution_files_safely(model, gurobi_output_path, gurobi_output_name):
    """
    Save solution files in multiple formats for maximum recoverability
    """
    if not (hasattr(model, 'SolCount') and model.SolCount > 0):
        print("No solutions to save")
        return False
    
    print(f"Saving solution files for {model.SolCount} solution(s)...")
    saved_files = []
    
    try:
        # 1. Save .sol file (most important)
        sol_file = os.path.join(gurobi_output_path, f"solution_{gurobi_output_name}.sol")
        model.write(sol_file)
        saved_files.append(sol_file)
        print(f"✓ Saved: {sol_file}")
    except Exception as e:
        print(f"✗ Could not save .sol file: {e}")
    
    try:
        # 2. Save .mst file (MIP start file - can be used to warm-start)
        mst_file = os.path.join(gurobi_output_path, f"solution_{gurobi_output_name}.mst")
        model.write(mst_file)
        saved_files.append(mst_file)
        print(f"✓ Saved: {mst_file}")
    except Exception as e:
        print(f"✗ Could not save .mst file: {e}")
    
    try:
        # 3. Save basic solution info to text file
        info_file = os.path.join(gurobi_output_path, f"solution_info_{gurobi_output_name}.txt")
        with open(info_file, 'w') as f:
            f.write(f"=== SOLUTION SUMMARY ===\n")
            f.write(f"Status: {model.status}\n")
            f.write(f"Objective Value: {model.ObjVal}\n")
            f.write(f"MIP Gap: {model.MIPGap * 100:.6f}%\n")
            f.write(f"Solution Count: {model.SolCount}\n")
            f.write(f"Variables: {model.NumVars}\n")
            f.write(f"Constraints: {model.NumConstrs}\n")
            f.write(f"\n=== NON-ZERO VARIABLES ===\n")
            
            # Save key non-zero variables (up to first 100 to avoid memory issues)
            var_count = 0
            for var in model.getVars():
                if abs(var.X) > 1e-6 and var_count < 100:
                    f.write(f"{var.VarName} = {var.X}\n")
                    var_count += 1
                elif var_count >= 100:
                    f.write(f"... (truncated, showing first 100 non-zero variables)\n")
                    break
        
        saved_files.append(info_file)
        print(f"✓ Saved: {info_file}")
        
    except Exception as e:
        print(f"✗ Could not save info file: {e}")
    
    print(f"Successfully saved {len(saved_files)} solution files")
    return len(saved_files) > 0

