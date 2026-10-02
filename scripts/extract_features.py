import os
import json
import re


# ================================================================
# Configuration
# ================================================================

RUN_TAG = os.environ.get("RUN_TAG", "run_test")

RUN_DIR = os.path.join(
    "systolic_project",
    "runs",
    RUN_TAG
)

OUTPUT_JSON = os.path.join(
    RUN_DIR,
    "features.json"
)


# ================================================================
# Utility functions
# ================================================================

def read_file(path):

    if not os.path.exists(path):
        return ""

    try:
        with open(path, "r", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def first_float(patterns, text):

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            try:
                return float(match.group(1))
            except (ValueError, TypeError):
                pass

    return None


def first_int(patterns, text):

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

    return None


# ================================================================
# Wirelength extraction
# ================================================================

def extract_wirelength():

    # Prefer detailed-route report.
    detailed_path = os.path.join(
        RUN_DIR,
        "wirelength_detailed.rpt"
    )

    text = read_file(detailed_path)

    # OpenROAD commonly prints:
    #
    # Total wirelength: XXXXX um
    #
    value = first_float([
        r"Total\s+wirelength\s*:\s*([0-9.eE+\-]+)\s*um",
        r"Total\s+wire\s+length\s*:\s*([0-9.eE+\-]+)\s*um",
        r"wirelength\s*[:=]\s*([0-9.eE+\-]+)"
    ], text)

    if value is not None:
        return value

    # Try final report.
    final_path = os.path.join(
        RUN_DIR,
        "wirelength_final.rpt"
    )

    text = read_file(final_path)

    value = first_float([
        r"Total\s+wirelength\s*:\s*([0-9.eE+\-]+)\s*um",
        r"Total\s+wire\s+length\s*:\s*([0-9.eE+\-]+)\s*um",
        r"wirelength\s*[:=]\s*([0-9.eE+\-]+)"
    ], text)

    if value is not None:
        return value

    # Try global-route report.
    global_path = os.path.join(
        RUN_DIR,
        "wirelength_global.rpt"
    )

    text = read_file(global_path)

    value = first_float([
        r"Total\s+wirelength\s*:\s*([0-9.eE+\-]+)\s*um",
        r"Total\s+wire\s+length\s*:\s*([0-9.eE+\-]+)\s*um",
        r"wirelength\s*[:=]\s*([0-9.eE+\-]+)"
    ], text)

    return value


# ================================================================
# Congestion extraction
# ================================================================

def extract_congestion():

    path = os.path.join(
        RUN_DIR,
        "congestion.rpt"
    )

    text = read_file(path)

    if not text:
        return None

    # Look for Total row:
    #
    # Total 460323 85090 18.48% 0 / 0 / 0
    #
    # We capture:
    # resource
    # demand
    # utilization
    # total overflow

    patterns = [

        r"^\s*Total\s+"
        r"(\d+)\s+"
        r"(\d+)\s+"
        r"([0-9.]+)%\s+"
        r"\d+\s*/\s*"
        r"\d+\s*/\s*"
        r"(\d+)",

        r"Total\s+"
        r"(\d+)\s+"
        r"(\d+)\s+"
        r"([0-9.]+)%\s+"
        r"\d+\s*/\s*"
        r"\d+\s*/\s*"
        r"(\d+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.IGNORECASE |
            re.MULTILINE
        )

        if match:

            resource = int(match.group(1))
            demand = int(match.group(2))
            utilization = float(match.group(3))
            overflow = int(match.group(4))

            return {
                "routing_resource": resource,
                "routing_demand": demand,
                "routing_utilization_pct": utilization,
                "routing_total_overflow": overflow
            }

    return None


# ================================================================
# Timing extraction
# ================================================================

def extract_timing():

    setup_path = os.path.join(
        RUN_DIR,
        "timing_setup.rpt"
    )

    hold_path = os.path.join(
        RUN_DIR,
        "timing_hold.rpt"
    )

    setup_text = read_file(setup_path)
    hold_text = read_file(hold_path)

    # OpenSTA/OpenROAD timing reports can vary slightly.
    # Search for explicit slack values.

    setup_values = re.findall(
        r"slack\s+\([^)]+\)\s+(-?[0-9.eE+\-]+)",
        setup_text,
        re.IGNORECASE
    )

    hold_values = re.findall(
        r"slack\s+\([^)]+\)\s+(-?[0-9.eE+\-]+)",
        hold_text,
        re.IGNORECASE
    )

    setup_values = [
        float(x)
        for x in setup_values
        if x not in ("", None)
    ]

    hold_values = [
        float(x)
        for x in hold_values
        if x not in ("", None)
    ]

    result = {
        "wns_setup_ns": None,
        "tns_setup_ns": None,
        "wns_hold_ns": None
    }

    if setup_values:

        result["wns_setup_ns"] = min(
            setup_values
        )

        negative_setup = [
            x for x in setup_values
            if x < 0
        ]

        if negative_setup:
            result["tns_setup_ns"] = sum(
                negative_setup
            )
        else:
            result["tns_setup_ns"] = 0.0

    if hold_values:

        result["wns_hold_ns"] = min(
            hold_values
        )

    return result


# ================================================================
# Cell/net extraction from Yosys report
# ================================================================

def extract_yosys_stats():

    path = os.path.join(
        RUN_DIR,
        "yosys_synth_area.rpt"
    )

    text = read_file(path)

    result = {
        "num_cells": None,
        "num_wires": None
    }

    value = first_int(
        [
            r"Number\s+of\s+cells\s*:\s*(\d+)"
        ],
        text
    )

    if value is not None:
        result["num_cells"] = value

    value = first_int(
        [
            r"Number\s+of\s+wires\s*:\s*(\d+)"
        ],
        text
    )

    if value is not None:
        result["num_wires"] = value

    return result


# ================================================================
# Main extraction
# ================================================================

def extract_features():

    print("=" * 70)
    print("FEATURE EXTRACTION")
    print("=" * 70)

    print(f"Run tag : {RUN_TAG}")
    print(f"Run dir : {RUN_DIR}")

    os.makedirs(
        RUN_DIR,
        exist_ok=True
    )

    # ------------------------------------------------------------
    # Base experiment parameters
    # ------------------------------------------------------------

    metrics = {

        "run_tag": RUN_TAG,

        "array_size":
            int(os.environ.get(
                "ARRAY_SIZE",
                4
            )),

        "data_width":
            int(os.environ.get(
                "DATA_WIDTH",
                8
            )),

        "utilization":
            float(os.environ.get(
                "UTIL",
                50
            )),

        "clk_period_ns":
            float(os.environ.get(
                "CLK_PERIOD",
                5.0
            )),

        # --------------------------------------------------------
        # Design size
        # --------------------------------------------------------

        "num_cells": None,
        "num_nets": None,
        "num_pins": None,
        "num_buffers": None,

        # --------------------------------------------------------
        # Physical
        # --------------------------------------------------------

        "die_area_u2": None,
        "core_area_u2": None,

        # --------------------------------------------------------
        # Routing
        # --------------------------------------------------------

        "wirelength_u": None,
        "via_count": None,
        "congestion_overflow_pct": None,

        # --------------------------------------------------------
        # Timing
        # --------------------------------------------------------

        "wns_setup_ps": None,
        "tns_setup_ps": None,
        "wns_hold_ps": None
    }

    # ============================================================
    # Yosys statistics
    # ============================================================

    yosys_stats = extract_yosys_stats()

    if yosys_stats["num_cells"] is not None:

        metrics["num_cells"] = \
            yosys_stats["num_cells"]

    # ============================================================
    # Wirelength
    # ============================================================

    wirelength = extract_wirelength()

    if wirelength is not None:

        metrics["wirelength_u"] = round(
            wirelength,
            3
        )

        print(
            f"[OK] Wirelength = "
            f"{metrics['wirelength_u']} um"
        )

    else:

        print(
            "[WARNING] Wirelength could not "
            "be extracted."
        )

    # ============================================================
    # Congestion
    # ============================================================

    congestion = extract_congestion()

    if congestion is not None:

        # The original 17-feature schema uses
        # congestion_overflow_pct.
        #
        # We store total overflow as the primary
        # congestion quantity.

        metrics["congestion_overflow_pct"] = \
            float(
                congestion[
                    "routing_total_overflow"
                ]
            )

        print(
            "[OK] Routing utilization = "
            f"{congestion['routing_utilization_pct']}%"
        )

        print(
            "[OK] Total routing overflow = "
            f"{congestion['routing_total_overflow']}"
        )

    else:

        print(
            "[WARNING] Congestion report "
            "could not be parsed."
        )

    # ============================================================
    # Timing
    # ============================================================

    timing = extract_timing()

    if timing["wns_setup_ns"] is not None:

        metrics["wns_setup_ps"] = round(
            timing["wns_setup_ns"] * 1000.0,
            3
        )

    if timing["tns_setup_ns"] is not None:

        metrics["tns_setup_ps"] = round(
            timing["tns_setup_ns"] * 1000.0,
            3
        )

    if timing["wns_hold_ns"] is not None:

        metrics["wns_hold_ps"] = round(
            timing["wns_hold_ns"] * 1000.0,
            3
        )

    # ============================================================
    # ODB extraction
    # ============================================================

    odb_path = os.path.join(
        RUN_DIR,
        "final.odb"
    )

    if os.path.exists(odb_path):

        print(
            "[INFO] final.odb exists."
        )

        # The exact Python API differs across
        # OpenROAD builds, so do not fabricate
        # database values when the API is unavailable.

        try:

            import openroad

            print(
                "[INFO] OpenROAD Python module "
                "available."
            )

        except ImportError:

            print(
                "[INFO] OpenROAD Python module "
                "not available."
            )

    # ============================================================
    # Derived validity fields
    # ============================================================

    metrics["valid_run"] = (
        os.path.exists(odb_path)
        and metrics["wirelength_u"] is not None
    )

    metrics["wirelength_available"] = (
        metrics["wirelength_u"] is not None
    )

    metrics["congestion_available"] = (
        metrics["congestion_overflow_pct"]
        is not None
    )

    metrics["timing_available"] = (
        metrics["wns_setup_ps"] is not None
    )

    # ============================================================
    # Save
    # ============================================================

    with open(
        OUTPUT_JSON,
        "w"
    ) as f:

        json.dump(
            metrics,
            f,
            indent=4
        )

    print()
    print("=" * 70)
    print("FEATURE EXTRACTION COMPLETE")
    print("=" * 70)
    print(f"Output: {OUTPUT_JSON}")

    for key, value in metrics.items():

        print(
            f"{key:30s}: {value}"
        )

    print("=" * 70)


if __name__ == "__main__":

    extract_features()
