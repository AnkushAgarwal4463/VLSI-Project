import os
import glob
import json
import pandas as pd

def build_clean_dataset(runs_dir="systolic_project/runs", output_csv="summary_output/dataset.csv"):
    # Target only top-level feature files to prevent nested directory duplication
    json_files = sorted(list(set(glob.glob(os.path.join(runs_dir, "**", "*_features.json"), recursive=True))))
    
    seen_tags = set()
    records = []

    for fpath in json_files:
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
                tag = data.get("run_tag")
                
                # Strict unique tag guard before DataFrame instantiation
                if tag and tag not in seen_tags:
                    seen_tags.add(tag)
                    records.append(data)
        except Exception as e:
            print(f"[WARNING] Could not parse {fpath}: {e}")

    df = pd.DataFrame(records)
    
    # Sort systematically by matrix design parameters
    sort_cols = [c for c in ["array_size", "data_width", "utilization", "clk_period_ns"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(by=sort_cols).reset_index(drop=True)

    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"[SUCCESS] Written {len(df)} unique records to {output_csv}")

if __name__ == "__main__":
    build_clean_dataset()
