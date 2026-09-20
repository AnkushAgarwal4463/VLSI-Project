import os
import re
import json
import glob

def parse_openroad_log(log_path):
    """Extract key metrics from openroad.log using regex parsing."""
    metrics = {
        "wirelength_u": None,
        "total_gate_area": None,
        "slack_ps": None,
        "total_power_mw": None,
        "routing_congested_nets": None
    }
    
    if not os.path.exists(log_path):
        return metrics

    with open(log_path, 'r') as f:
        log_data = f.read()

    # Extract Total Wirelength
    wl_match = re.search(r"Total wire length = ([\d\.]+)", log_data)
    if wl_match:
        metrics["wirelength_u"] = float(wl_match.group(1))

    # Extract Total Gate Area
    area_match = re.search(r"Design area ([\d\.]+) u\^2", log_data)
    if area_match:
        metrics["total_gate_area"] = float(area_match.group(1))

    # Extract Worst Negative Slack (WNS)
    wns_match = re.search(r"worst slack ([-?\d\.]+)", log_data)
    if wns_match:
        metrics["slack_ps"] = float(wns_match.group(1)) * 1000.0  # convert ns to ps

    # Extract Total Internal + Switch + Leakage Power
    power_match = re.search(r"Total\s+([\d\.e\-]+)\s+([\d\.e\-]+)\s+([\d\.e\-]+)\s+([\d\.e\-]+)", log_data)
    if power_match:
        metrics["total_power_mw"] = float(power_match.group(4)) * 1000.0  # convert Watts to mW

    # Extract Congested Nets Count
    congest_match = re.search(r"Found ([\d]+) congested nets", log_data)
    if congest_match:
        metrics["routing_congested_nets"] = int(congest_match.group(1))

    return metrics


def main():
    run_dir = os.environ.get("RUN_DIR")
    if not run_dir:
        # Fallback search if RUN_DIR environment variable is not set directly
        run_dirs = glob.glob("systolic_project/runs/*")
        if run_dirs:
            run_dir = run_dirs[0]
        else:
            raise ValueError("RUN_DIR environment variable is not defined.")

    run_tag = os.environ.get("RUN_TAG", os.path.basename(run_dir))
    
    # Extract matrix sweep parameters from environment variables
    array_size = int(os.environ.get("ARRAY_SIZE", 4))
    data_width = int(os.environ.get("DATA_WIDTH", 8))
    utilization = float(os.environ.get("UTIL", 50))
    clk_period_ns = float(os.environ.get("CLK_PERIOD", 10.0))

    # Parse logs inside $RUN_DIR
    log_path = os.path.join(run_dir, "openroad.log")
    extracted_metrics = parse_openroad_log(log_path)

    # Combine metadata, hyper-parameters, and extracted PPA metrics
    feature_record = {
        "run_tag": run_tag,
        "array_size": array_size,
        "data_width": data_width,
        "utilization": utilization,
        "clk_period_ns": clk_period_ns,
        "wirelength_u": extracted_metrics["wirelength_u"],
        "total_gate_area": extracted_metrics["total_gate_area"],
        "slack_ps": extracted_metrics["slack_ps"],
        "total_power_mw": extracted_metrics["total_power_mw"],
        "routing_congested_nets": extracted_metrics["routing_congested_nets"]
    }

    # Save to JSON file inside run directory
    output_json_path = os.path.join(run_dir, f"{run_tag}_features.json")
    with open(output_json_path, 'w') as f:
        json.dump(feature_record, f, indent=2)

    print(f"Successfully generated feature extraction JSON: {output_json_path}")

if __name__ == "__main__":
    main()
