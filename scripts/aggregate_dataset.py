import os
import glob
import json
import argparse
import pandas as pd

def aggregate_features(runs_dir="downloaded_artifacts", output_csv="summary_output/systolic_array_sweep_dataset.csv"):
    """Find all feature JSON files across workspace directories and aggregate them into a CSV."""
    
    search_dirs = [runs_dir, "systolic_project/runs", "."]
    json_files = []

    for d in search_dirs:
        if os.path.exists(d):
            found = glob.glob(os.path.join(d, "**", "*_features.json"), recursive=True)
            found += glob.glob(os.path.join(d, "*_features.json"))
            json_files.extend(found)
            
    json_files = sorted(list(set(json_files)))

    if not json_files:
        print(f"[ERROR] No *_features.json files found across search directories: {search_dirs}")
        exit(1)

    print(f"[INFO] Found {len(json_files)} feature file(s) to process...")

    records = []
    for file_path in json_files:
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                records.append(data)
        except Exception as e:
            print(f"[WARNING] Error reading {file_path}: {e}")

    if not records:
        print("[ERROR] Failed to load any records from found JSON files.")
        exit(1)

    df = pd.DataFrame(records)

    # Harmonize column names
    if "clk_period" in df.columns and "clk_period_ns" not in df.columns:
        df.rename(columns={"clk_period": "clk_period_ns"}, inplace=True)

    # Priority ordering for output CSV
    priority_cols = [
        "run_tag",
        "array_size",
        "data_width",
        "utilization",
        "clk_period_ns",
        "num_cells",
        "die_area_u2",
        "wirelength_u",
        "slack_ps"
    ]

    existing_priority_cols = [col for col in priority_cols if col in df.columns]
    other_cols = [col for col in df.columns if col not in priority_cols]
    final_cols = existing_priority_cols + other_cols

    df = df[final_cols]

    # Sort rows systematically by sweep variables
    sort_keys = [c for c in ["array_size", "data_width", "utilization", "clk_period_ns"] if c in df.columns]
    if sort_keys:
        df = df.sort_values(by=sort_keys).reset_index(drop=True)

    # Create destination folder if missing
    output_dir = os.path.dirname(output_csv)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    
    df.to_csv(output_csv, index=False)
    print(f"[SUCCESS] Successfully aggregated {len(records)} run outputs into '{output_csv}'")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate OpenROAD run feature JSONs into CSV.")
    parser.add_argument("--runs_dir", default="downloaded_artifacts", help="Directory to search for *_features.json files")
    parser.add_argument("--output_csv", default="summary_output/systolic_array_sweep_dataset.csv", help="Path to output CSV file")
    args = parser.parse_args()

    aggregate_features(runs_dir=args.runs_dir, output_csv=args.output_csv)
