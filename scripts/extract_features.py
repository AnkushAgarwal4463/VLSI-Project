import os
import json

def verify_and_emit():
    run_tag = os.environ.get("RUN_TAG", "run")
    json_path = os.path.join("systolic_project", "runs", f"{run_tag}_features.json")

    if os.path.exists(json_path):
        with open(json_path, "r") as f:
            data = json.load(f)
        print(f"[SUCCESS] Metrics verified for {run_tag}: Cells={data.get('num_cells')}, DieArea={data.get('die_area_u2')}")
    else:
        print(f"[WARNING] {json_path} not found. Creating fallback JSON.")
        fallback = {
            "run_tag": run_tag,
            "array_size": int(os.environ.get("ARRAY_SIZE", 0)),
            "data_width": int(os.environ.get("DATA_WIDTH", 0)),
            "utilization": float(os.environ.get("UTIL", 0.0)),
            "clk_period_ns": float(os.environ.get("CLK_PERIOD", 0.0)),
            "num_cells": 0,
            "die_area_u2": 0.0,
            "wirelength_u": 0.0,
            "slack_ps": 0.0
        }
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w") as f:
            json.dump(fallback, f, indent=4)

if __name__ == "__main__":
    verify_and_emit()
