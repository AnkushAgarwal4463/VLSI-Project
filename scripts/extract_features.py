```python
import os
import json
import re


# ==============================================================================
# Utility Functions
# ==============================================================================

def read_file(path):
    """Read a text file safely."""
    if not os.path.exists(path):
        return ""

    try:
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def first_float(patterns, text, default=0.0):
    """Try multiple regex patterns and return the first float found."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)

        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                pass

    return default


def first_int(patterns, text, default=0):
    """Try multiple regex patterns and return the first integer found."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)

        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                pass

    return default


# ==============================================================================
# Main Extraction
# ==============================================================================

def extract_and_emit():

    # --------------------------------------------------------------------------
    # Environment
    # --------------------------------------------------------------------------

    run_tag = os.environ.get("RUN_TAG", "run_test")

    run_dir = os.path.join(
        "systolic_project",
        "runs",
        run_tag
    )

    # IMPORTANT:
    # Features are stored INSIDE the run directory.
    json_path = os.path.join(
        run_dir,
        "features.json"
    )

    odb_path = os.path.join(
        run_dir,
        "final.odb"
    )

    # --------------------------------------------------------------------------
    # Input parameters
    # --------------------------------------------------------------------------

    array_size = int(
        os.environ.get("ARRAY_SIZE", 4)
    )

    data_width = int(
        os.environ.get("DATA_WIDTH", 8)
    )

    utilization = float(
        os.environ.get("UTIL", 50.0)
    )

    clk_period = float(
        os.environ.get("CLK_PERIOD", 5.0)
    )

    # --------------------------------------------------------------------------
    # Initialize feature schema
    # --------------------------------------------------------------------------

    metrics = {

        # ==============================================================
        # 1-5: Architectural / SDC inputs
        # ==============================================================

        "run_tag": run_tag,

        "array_size": array_size,

        "data_width": data_width,

        "utilization": utilization,

        "clk_period_ns": clk_period,


        # ==============================================================
        # 6-11: Physical design / gate-level features
        # ==============================================================

        "num_cells": 0,

        "num_nets": 0,

        "num_pins": 0,

        "num_buffers": 0,

        "die_area_u2": 0.0,

        "core_area_u2": 0.0,


        # ==============================================================
        # 12-14: Routing / congestion
        # ==============================================================

        "wirelength_u": 0.0,

        "via_count": 0,

        "congestion_overflow_pct": 0.0,


        # ==============================================================
        # 15-17: Timing
        # ==============================================================

        "wns_setup_ps": 0.0,

        "tns_setup_ps": 0.0,

        "wns_hold_ps": 0.0
    }


    # ==========================================================================
    # 1. Check database
    # ==========================================================================

    if not os.path.exists(odb_path):

        print(
            f"[WARNING] final.odb not found: {odb_path}"
        )

    else:

        print(
            f"[INFO] Found OpenROAD database: {odb_path}"
        )


    # ==========================================================================
    # 2. Parse OpenROAD logs / reports
    # ==========================================================================

    openroad_log = read_file(
        os.path.join(
            run_dir,
            "openroad_log.txt"
        )
    )

    timing_setup = read_file(
        os.path.join(
            run_dir,
            "timing_setup.rpt"
        )
    )

    timing_hold = read_file(
        os.path.join(
            run_dir,
            "timing_hold.rpt"
        )
    )

    wirelength_report = read_file(
        os.path.join(
            run_dir,
            "wire_length.rpt"
        )
    )

    synth_report = read_file(
        os.path.join(
            run_dir,
            "yosys_synth_area.rpt"
        )
    )

    # ==========================================================================
    # 3. Yosys cell count
    # ==========================================================================

    metrics["num_cells"] = first_int(
        [
            r"Number of cells:\s*([0-9]+)",
            r"Number of cells\s+([0-9]+)"
        ],
        synth_report,
        0
    )


    # ==========================================================================
    # 4. Yosys / OpenROAD net count
    # ==========================================================================

    metrics["num_nets"] = first_int(
        [
            r"Number of wires:\s*([0-9]+)",
            r"Number of nets:\s*([0-9]+)",
            r"nets\s*[:=]\s*([0-9]+)"
        ],
        synth_report + "\n" + openroad_log,
        0
    )


    # ==========================================================================
    # 5. Pin count
    # ==========================================================================

    metrics["num_pins"] = first_int(
        [
            r"Number of ports:\s*([0-9]+)",
            r"Number of pins:\s*([0-9]+)",
            r"pins\s*[:=]\s*([0-9]+)"
        ],
        synth_report + "\n" + openroad_log,
        0
    )


    # ==========================================================================
    # 6. Buffer count
    # ==========================================================================

    buffer_matches = re.findall(
        r"\b(buf[a-zA-Z0-9_]*|clkbuf[a-zA-Z0-9_]*)\b",
        synth_report + "\n" + openroad_log,
        re.IGNORECASE
    )

    metrics["num_buffers"] = len(buffer_matches)


    # ==========================================================================
    # 7. Die area
    # ==========================================================================

    die_x0 = first_float(
        [
            r"Die\s*:\s*([0-9.eE+-]+)"
        ],
        openroad_log,
        0.0
    )

    # Try to extract the full die coordinates.
    die_match = re.search(
        r"Die\s*:\s*"
        r"([0-9.eE+-]+)\s+"
        r"([0-9.eE+-]+)\s+"
        r"([0-9.eE+-]+)\s+"
        r"([0-9.eE+-]+)",
        openroad_log,
        re.IGNORECASE
    )

    if die_match:

        x0 = float(die_match.group(1))
        y0 = float(die_match.group(2))
        x1 = float(die_match.group(3))
        y1 = float(die_match.group(4))

        metrics["die_area_u2"] = round(
            abs(x1 - x0) * abs(y1 - y0),
            2
        )


    # ==========================================================================
    # 8. Core area
    # ==========================================================================

    core_match = re.search(
        r"Core\s*:\s*"
        r"([0-9.eE+-]+)\s+"
        r"([0-9.eE+-]+)\s+"
        r"([0-9.eE+-]+)\s+"
        r"([0-9.eE+-]+)",
        openroad_log,
        re.IGNORECASE
    )

    if core_match:

        x0 = float(core_match.group(1))
        y0 = float(core_match.group(2))
        x1 = float(core_match.group(3))
        y1 = float(core_match.group(4))

        metrics["core_area_u2"] = round(
            abs(x1 - x0) * abs(y1 - y0),
            2
        )


    # ==========================================================================
    # 9. Wirelength
    # ==========================================================================

    metrics["wirelength_u"] = first_float(
        [
            r"total\s+wire\s+length\s*[:=]\s*([0-9.eE+-]+)",
            r"wire\s+length\s*[:=]\s*([0-9.eE+-]+)",
            r"Total wire length\s*[:=]\s*([0-9.eE+-]+)"
        ],
        wirelength_report,
        0.0
    )


    # ==========================================================================
    # 10. Via count
    # ==========================================================================

    metrics["via_count"] = first_int(
        [
            r"vias?\s*[:=]\s*([0-9]+)",
            r"Total vias?\s*[:=]\s*([0-9]+)"
        ],
        openroad_log,
        0
    )


    # ==========================================================================
    # 11. Congestion
    # ==========================================================================

    congestion_value = first_float(
        [
            r"overflow\s*[:=]\s*([0-9.eE+-]+)",
            r"congestion\s+overflow\s*[:=]\s*([0-9.eE+-]+)",
            r"total\s+overflow\s*[:=]\s*([0-9.eE+-]+)"
        ],
        openroad_log,
        0.0
    )

    metrics["congestion_overflow_pct"] = round(
        congestion_value,
        4
    )


    # ==========================================================================
    # 12. Setup WNS
    # ==========================================================================

    setup_wns = first_float(
        [
            r"wns\s*[:=]\s*(-?[0-9.eE+-]+)",
            r"Worst\s+Slack\s*[:=]\s*(-?[0-9.eE+-]+)",
            r"worst\s+slack\s*(-?[0-9.eE+-]+)"
        ],
        timing_setup,
        0.0
    )

    metrics["wns_setup_ps"] = round(
        setup_wns * 1000.0,
        2
    )


    # ==========================================================================
    # 13. Setup TNS
    # ==========================================================================

    setup_tns = first_float(
        [
            r"tns\s*[:=]\s*(-?[0-9.eE+-]+)",
            r"Total\s+Negative\s+Slack\s*[:=]\s*(-?[0-9.eE+-]+)",
            r"total\s+negative\s+slack\s*(-?[0-9.eE+-]+)"
        ],
        timing_setup,
        0.0
    )

    metrics["tns_setup_ps"] = round(
        setup_tns * 1000.0,
        2
    )


    # ==========================================================================
    # 14. Hold WNS
    # ==========================================================================

    hold_wns = first_float(
        [
            r"wns\s*[:=]\s*(-?[0-9.eE+-]+)",
            r"Worst\s+Slack\s*[:=]\s*(-?[0-9.eE+-]+)",
            r"worst\s+slack\s*(-?[0-9.eE+-]+)"
        ],
        timing_hold,
        0.0
    )

    metrics["wns_hold_ps"] = round(
        hold_wns * 1000.0,
        2
    )


    # ==========================================================================
    # 15. Derived features
    # ==========================================================================

    # These are useful for ML and sanity checking.

    if metrics["core_area_u2"] > 0:

        metrics["cell_density_pct"] = round(
            (
                metrics["num_cells"] /
                metrics["core_area_u2"]
            ) * 100.0,
            4
        )

    else:

        metrics["cell_density_pct"] = 0.0


    if metrics["array_size"] > 0:

        metrics["pe_count"] = (
            metrics["array_size"] *
            metrics["array_size"]
        )

    else:

        metrics["pe_count"] = 0


    # ==========================================================================
    # 16. Extraction status
    # ==========================================================================

    metrics["odb_exists"] = os.path.exists(
        odb_path
    )

    metrics["reports_available"] = {
        "synth_report": os.path.exists(
            os.path.join(
                run_dir,
                "yosys_synth_area.rpt"
            )
        ),

        "openroad_log": os.path.exists(
            os.path.join(
                run_dir,
                "openroad_log.txt"
            )
        ),

        "timing_setup": os.path.exists(
            os.path.join(
                run_dir,
                "timing_setup.rpt"
            )
        ),

        "timing_hold": os.path.exists(
            os.path.join(
                run_dir,
                "timing_hold.rpt"
            )
        ),

        "wirelength": os.path.exists(
            os.path.join(
                run_dir,
                "wire_length.rpt"
            )
        )
    }


    # ==========================================================================
    # 17. Save JSON
    # ==========================================================================

    os.makedirs(
        run_dir,
        exist_ok=True
    )

    with open(
        json_path,
        "w"
    ) as f:

        json.dump(
            metrics,
            f,
            indent=4
        )


    print(
        f"[SUCCESS] Feature extraction completed."
    )

    print(
        f"[SUCCESS] Saved: {json_path}"
    )

    print(
        json.dumps(
            metrics,
            indent=4
        )
    )


# ==============================================================================
# Entry point
# ==============================================================================

if __name__ == "__main__":
    extract_and_emit()
```
