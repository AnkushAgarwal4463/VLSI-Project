import os
import glob
import json
import argparse
import pandas as pd

def aggregate_features(runs_dir="systolic_project/runs", output_csv="dataset/placement_dataset_real.csv"):
    """Find all JSON feature files and aggregate them into a master CSV dataset."""
    
    # 1. Search in specified directory first; fall back to downloaded_artifacts if missing
    search_pattern = os.path.join(runs_dir, "**", "*_features.json")
    json_files = glob.glob(search_pattern, recursive=True)

    if not json_files and os.path.exists("downloaded_artifacts"):
        print("No feature files in primary runs_dir. Searching 'downloaded_artifacts'...")
        search_pattern = os.path.join("downloaded_artifacts", "**", "*_features.json")
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

    # 2. Harmonize potential clock period column names
    if "clk_period" in df.columns and "clk_period_ns" not in df.columns:
        df.rename(columns={"clk_period": "clk_period_ns"}, inplace=True)

    # 3. Define exact priority column order
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

    # 4. Sort dataset by design matrix parameters
    sort_keys = [c for c in ["array_size", "data_width", "utilization", "clk_period_ns", "clk_period"] if c in df.columns]
    if sort_keys:
        df = df.sort_values(by=sort_keys).reset_index(drop=True)

    # 5. Create destination output directory if missing
    output_dir = os.path.dirname(output_csv)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    # Save aggregated output CSV
    df.to_csv(output_csv, index=False)
    print(f"Successfully aggregated {len(records)} run outputs into '{output_csv}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate OpenROAD run feature JSONs into CSV.")
    parser.add_argument("--runs_dir", default="systolic_project/runs", help="Directory to search for *_features.json files")
    parser.add_argument("--output_csv", default="dataset/placement_dataset_real.csv", help="Path to output CSV file")
    args = parser.parse_args()

    aggregate_features(runs_dir=args.runs_dir, output_csv=args.output_csv)
