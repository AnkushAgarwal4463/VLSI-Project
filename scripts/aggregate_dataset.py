import os
import glob
import json
import pandas as pd

# Define the full 17-feature schema with default fallback types
SCHEMA_DEFAULTS = {
    "run_tag": "unknown",
    "array_size": 0,
    "data_width": 0,
    "utilization": 0.0,
    "clk_period_ns": 0.0,
    "num_cells": 0,
    "num_nets": 0,
    "num_pins": 0,
    "num_buffers": 0,
    "die_area_u2": 0.0,
    "core_area_u2": 0.0,
    "wirelength_u": 0.0,
    "via_count": 0,
    "congestion_overflow_pct": 0.0,
    "wns_setup_ps": 0.0,
    "tns_setup_ps": 0.0,
    "wns_hold_ps": 0.0
}

FEATURE_COLUMNS = list(SCHEMA_DEFAULTS.keys())

def build_clean_dataset(runs_dir="systolic_project/runs", output_csv="summary_output/dataset.csv"):
    # Target feature JSON files recursively across all run subdirectories
    json_files = sorted(list(set(glob.glob(os.path.join(runs_dir, "**", "*_features.json"), recursive=True))))
    
    seen_tags = set()
    records = []

    print(f"[INFO] Scanning '{runs_dir}' for feature JSON files...")

    for fpath in json_files:
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
                
                # Extract run tag for deduplication
                tag = data.get("run_tag")
                if not tag or tag in seen_tags:
                    continue
                
                seen_tags.add(tag)
                
                # Fill missing keys to guarantee all 17 features are represented
                clean_record = {}
                for key, default_val in SCHEMA_DEFAULTS.items():
                    val = data.get(key)
                    if val is None:
                        clean_record[key] = default_val
                    else:
                        # Cast to match default type
                        clean_record[key] = type(default_val)(val) if not isinstance(default_val, float) else float(val)
                
                records.append(clean_record)

        except Exception as e:
            print(f"[WARNING] Could not parse {fpath}: {e}")

    # Build DataFrame
    if records:
        df = pd.DataFrame(records)[FEATURE_COLUMNS]
        
        # Sort systematically by design parameter matrix
        sort_cols = [c for c in ["array_size", "data_width", "utilization", "clk_period_ns"] if c in df.columns]
        if sort_cols:
            df = df.sort_values(by=sort_cols).reset_index(drop=True)
    else:
        print("[WARNING] No JSON feature files were found. Initializing empty DataFrame with 17-feature schema.")
        df = pd.DataFrame(columns=FEATURE_COLUMNS)

    # Ensure output directory exists and export CSV
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    df.to_csv(output_csv, index=False)
    
    print(f"[SUCCESS] Written {len(df)} records across {len(FEATURE_COLUMNS)} features to '{output_csv}'")

if __name__ == "__main__":
    build_clean_dataset()
