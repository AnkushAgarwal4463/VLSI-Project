import os
import re
import json

def parse_logs():
    # 1. Fetch Environment Variables
    run_dir = os.environ.get("RUN_DIR", "systolic_project/runs")
    run_tag = os.environ.get("RUN_TAG", "run")
    
    array_size = int(os.environ.get("ARRAY_SIZE", 0))
    data_width = int(os.environ.get("DATA_WIDTH", 0))
    utilization = float(os.environ.get("UTIL", 0.0))
    clk_period = float(os.environ.get("CLK_PERIOD", 0.0))

    # 2. Flexible Log Location Checks
    synth_log_paths = [
        os.path.join("systolic_project", "synth", "synth_log.txt"),
        os.path.join(run_dir, "yosys.log")
    ]
    
    openroad_log_paths = [
        os.path.join("systolic_project", "runs", f"{run_tag}_log.txt"),
        os.path.join(run_dir, "openroad.log")
    ]

    num_cells = 0
    die_area = 0.0
    wirelength_u = 0.0
    slack_ps = 0.0

    # 3. Parse Synthesis Log for Cell Counts
    for yosys_path in synth_log_paths:
        if os.path.exists(yosys_path):
            with open(yosys_path, "r") as f:
                content = f.read()
                match = re.search(r"Number of cells:\s+(\d+)", content)
                if match:
                    num_cells = int(match.group(1))
            break

    # 4. Parse OpenROAD Log for Physical Dimensions & Metrics
    for openroad_path in openroad_log_paths:
        if os.path.exists(openroad_path):
            with open(openroad_path, "r") as f:
                content = f.read()

                # Parse Die Area (x0, y0) (x1, y1)
                die_match = re.search(
                    r"Die area:\s*\(?\s*([0-9.]+)\s+([0-9.]+)\s*\)?\s*\(?\s*([0-9.]+)\s+([0-9.]+)\s*\)?",
                    content,
                    re.IGNORECASE
                )
                if die_match:
                    x0, y0, x1, y1 = map(float, die_match.groups())
                    die_area = (x1 - x0) * (y1 - y0)
                else:
                    # Fallback coordinate search
                    bbox_match = re.search(r"die_area.*?([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)\s+([0-9.]+)", content, re.IGNORECASE)
                    if bbox_match:
                        x0, y0, x1, y1 = map(float, bbox_match.groups())
                        die_area = (x1 - x0) * (y1 - y0)

                # Optional: Extract Total Wirelength
                wl_match = re.search(r"Total wirelength:\s*([0-9.]+)\s*u?", content, re.IGNORECASE)
                if wl_match:
                    wirelength_u = float(wl_match.group(1))

                # Optional: Extract Worst Slack (ps)
                slack_match = re.search(r"wns\s*([-\d.]+)", content, re.IGNORECASE)
                if slack_match:
                    slack_ps = float(slack_match.group(1))
            break

    features = {
        "run_tag": run_tag,
        "array_size": array_size,
        "data_width": data_width,
        "utilization": utilization,
        "clk_period_ns": clk_period,
        "num_cells": num_cells,
        "die_area_u2": round(die_area, 2),
        "wirelength_u": round(wirelength_u, 2),
        "slack_ps": slack_ps
    }

    # 5. Output JSON to root runs/ folder to match upload-artifact
    output_path = os.path.join("systolic_project", "runs", f"{run_tag}_features.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, "w") as f:
        json.dump(features, f, indent=4)

    print(f"[SUCCESS] Features successfully extracted to: {output_path}")

if __name__ == "__main__":
    parse_logs()
