import os
import re
import json

def parse_logs():
    run_dir = os.environ.get("RUN_DIR", ".")
    run_tag = os.environ.get("RUN_TAG", "run")
    
    array_size = int(os.environ.get("ARRAY_SIZE", 0))
    data_width = int(os.environ.get("DATA_WIDTH", 0))
    utilization = float(os.environ.get("UTIL", 0.0))
    clk_period = float(os.environ.get("CLK_PERIOD", 0.0))

    yosys_log_path = os.path.join(run_dir, "yosys.log")
    openroad_log_path = os.path.join(run_dir, "openroad.log")

    num_cells = 0
    die_area = 0.0

    # Parse Yosys log for cell counts
    if os.path.exists(yosys_log_path):
        with open(yosys_log_path, "r") as f:
            content = f.read()
            match = re.search(r"Number of cells:\s+(\d+)", content)
            if match:
                num_cells = int(match.group(1))

    # Parse OpenROAD log for physical dimensions
    if os.path.exists(openroad_log_path):
        with open(openroad_log_path, "r") as f:
            for line in f:
                if "die area" in line.lower() or "die_area" in line.lower():
                    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", line)
                    if numbers:
                        die_area = float(numbers[0])

    features = {
        "run_tag": run_tag,
        "array_size": array_size,
        "data_width": data_width,
        "utilization": utilization,
        "clk_period": clk_period,
        "num_cells": num_cells,
        "die_area": die_area
    }

    output_path = os.path.join(run_dir, f"{run_tag}_features.json")
    with open(output_path, "w") as f:
        json.dump(features, f, indent=4)

    print(f"Features successfully extracted to: {output_path}")

if __name__ == "__main__":
    parse_logs()
