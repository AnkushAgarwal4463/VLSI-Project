import os
import glob
import json
import pandas as pd

def aggregate_features(runs_dir="systolic_project/runs", output_csv="dataset/placement_dataset_real.csv"):
    """Find all JSON feature files and aggregate them into a master CSV dataset."""
    search_pattern = os.path.join(runs_dir, "**", "*_features.json")
    json_files = glob.glob(search_pattern, recursive=True)

    if not json_files:
        print(f"No feature JSON files found matching pattern: {search_pattern}")
        return

    records = []
    for file_path in json_files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                records.append(data)
        except Exception as e:
            print(f"Error reading {file_path}: {e}")

    df = pd.DataFrame(records)

    # Define exact priority column order
    priority_cols = [
        "run_tag",
        "array_size",
        "data_width",
        "utilization",
        "clk_period_ns",
        "wirelength_u",
        "total_gate_area",
        "slack_ps",
        "total_power_mw",
        "routing_congested_nets"
    ]

    # Reorder columns that exist and append any extra columns found
    existing_priority_cols = [col for col in priority_cols if col in df.columns]
    other_cols = [col for col in df.columns if col not in priority_cols]
    final_cols = existing_priority_cols + other_cols

    df = df[final_cols]

    # Sort dataset by array size, data width, utilization, and clock period
    sort_keys = [c for c in ["array_size", "data_width", "utilization", "clk_period_ns"] if c in df.columns]
    if sort_keys:
        df = df.sort_values(by=sort_keys).reset_index(drop=True)

    # Create destination output directory if missing
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    
    # Save aggregated output CSV
    df.to_csv(output_csv, index=False)
    print(f"Successfully aggregated {len(records)} run outputs into {output_csv}")

if __name__ == "__main__":
    aggregate_features()
