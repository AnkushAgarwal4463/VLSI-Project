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
# Utilities
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
            re.IGNORECASE | re.MULTILINE
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
            re.IGNORECASE | re.MULTILINE
        )

        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass

    return None


# ================================================================
# Design area
# ================================================================

def extract_area():

    path = os.path.join(
        RUN_DIR,
        "design_area.rpt"
    )

    text = read_file(path)

    result = {
        "die_area_u2": None,
        "core_area_u2": None
    }

    if not text:
        return result

    # Common OpenROAD area forms.
    die = first_float([
        r"Die\s+area\s*[:=]\s*([0-9.eE+\-]+)",
        r"die\s+area\s*[:=]\s*([0-9.eE+\-]+)",
    ], text)

    core = first_float([
        r"Core\s+area\s*[:=]\s*([0-9.eE+\-]+)",
        r"core\s+area\s*[:=]\s*([0-9.eE+\-]+)",
    ], text)

    if die is not None:
        result["die_area_u2"] = die

    if core is not None:
        result["core_area_u2"] = core

    # If the report gives rectangles instead of area directly,
    # calculate area from coordinates.
    if result["die_area_u2"] is None:

        match = re.search(
            r"die\s+area.*?"
            r"([0-9.eE+\-]+)\s+"
            r"([0-9.eE+\-]+)\s+"
            r"([0-9.eE+\-]+)\s+"
            r"([0-9.eE+\-]+)",
            text,
            re.IGNORECASE
        )

        if match:
            x0, y0, x1, y1 = map(float, match.groups())

            result["die_area_u2"] = abs(
                (x1 - x0) * (y1 - y0)
            )

    return result


# ================================================================
# Cell / net statistics
# ================================================================

def extract_design_stats():

    result = {
        "num_cells": None,
        "num_nets": None,
        "num_pins": None,
        "num_buffers": None
    }

    # ------------------------------------------------------------
    # OpenROAD cell usage
    # ------------------------------------------------------------

    cell_path = os.path.join(
        RUN_DIR,
        "cell_usage.rpt"
    )

    cell_text = read_file(cell_path)

    if cell_text:

        # Try total/summary forms first.
        result["num_cells"] = first_int([
            r"Total\s+instances\s*[:=]\s*(\d+)",
            r"Total\s+cells\s*[:=]\s*(\d+)",
            r"Number\s+of\s+instances\s*[:=]\s*(\d+)",
            r"Number\s+of\s+cells\s*[:=]\s*(\d+)"
        ], cell_text)

        # Count instances if the report lists them individually.
        if result["num_cells"] is None:

            matches = re.findall(
                r"^\s*(\d+)\s+\S+",
                cell_text,
                re.MULTILINE
            )

            if matches:
                result["num_cells"] = sum(
                    int(x) for x in matches
                )

    # ------------------------------------------------------------
    # OpenROAD log
    # ------------------------------------------------------------

    log_path = os.path.join(
        RUN_DIR,
        "openroad_log.txt"
    )

    log_text = read_file(log_path)

    # ------------------------------------------------------------
    # Nets
    # ------------------------------------------------------------

    result["num_nets"] = first_int([
        r"Number\s+of\s+nets\s*:\s*(\d+)",
        r"nets\s*:\s*(\d+)"
    ], log_text)

    # ------------------------------------------------------------
    # Pins
    # ------------------------------------------------------------

    result["num_pins"] = first_int([
        r"Number\s+of\s+pins\s*:\s*(\d+)",
        r"pins\s*:\s*(\d+)"
    ], log_text)

    # ------------------------------------------------------------
    # Buffers
    # ------------------------------------------------------------

    result["num_buffers"] = first_int([
        r"Number\s+of\s+buffers\s*:\s*(\d+)",
        r"buffers\s*:\s*(\d+)"
    ], log_text)

    return result


# ================================================================
# Wirelength
# ================================================================

def extract_wirelength():

    reports = [
        "wirelength_detailed.rpt",
        "wirelength_global.rpt"
    ]

    patterns = [
        r"Total\s+wirelength\s*:\s*"
        r"([0-9.eE+\-]+)\s*(?:um|micron)",

        r"Total\s+wire\s+length\s*:\s*"
        r"([0-9.eE+\-]+)\s*(?:um|micron)",

        r"wirelength\s*[:=]\s*"
        r"([0-9.eE+\-]+)"
    ]

    for filename in reports:

        path = os.path.join(
            RUN_DIR,
            filename
        )

        text = read_file(path)

        if not text:
            continue

        value = first_float(
            patterns,
            text
        )

        if value is not None:
            return value

    return None


# ================================================================
# Congestion
# ================================================================

def extract_congestion():

    candidates = [
        "congestion.rpt",
        "route_status_final.rpt"
    ]

    for filename in candidates:

        path = os.path.join(
            RUN_DIR,
            filename
        )

        text = read_file(path)

        if not text:
            continue

        # Total overflow
        overflow = first_int([
            r"Total\s+overflow\s*[:=]\s*(\d+)",
            r"overflow\s*[:=]\s*(\d+)"
        ], text)

        # Overflow may appear as a number after
        # routing-resource statistics.
        if overflow is None:

            match = re.search(
                r"Total.*?"
                r"overflow.*?"
                r"(\d+)",
                text,
                re.IGNORECASE |
                re.DOTALL
            )

            if match:
                overflow = int(match.group(1))

        if overflow is not None:
            return overflow

    return None


# ================================================================
# Via count
# ================================================================

def extract_vias():

    path = os.path.join(
        RUN_DIR,
        "route_status_final.rpt"
    )

    text = read_file(path)

    if not text:
        return None

    return first_int([
        r"Total\s+vias\s*[:=]\s*(\d+)",
        r"vias\s*[:=]\s*(\d+)",
        r"Via\s+count\s*[:=]\s*(\d+)"
    ], text)


# ================================================================
# Timing
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

    result = {
        "wns_setup_ns": None,
        "tns_setup_ns": None,
        "wns_hold_ns": None
    }

    # ------------------------------------------------------------
    # Prefer summary WNS/TNS if available
    # ------------------------------------------------------------

    result["wns_setup_ns"] = first_float([
        r"wns\s*[:=]\s*(-?[0-9.eE+\-]+)",
        r"worst\s+slack\s*[:=]\s*(-?[0-9.eE+\-]+)"
    ], setup_text)

    result["tns_setup_ns"] = first_float([
        r"tns\s*[:=]\s*(-?[0-9.eE+\-]+)",
        r"total\s+negative\s+slack\s*[:=]\s*(-?[0-9.eE+\-]+)"
    ], setup_text)

    result["wns_hold_ns"] = first_float([
        r"wns\s*[:=]\s*(-?[0-9.eE+\-]+)",
        r"worst\s+slack\s*[:=]\s*(-?[0-9.eE+\-]+)"
    ], hold_text)

    # ------------------------------------------------------------
    # Fallback: extract individual slack values
    # ------------------------------------------------------------

    if result["wns_setup_ns"] is None:

        values = re.findall(
            r"slack\s+\([^)]+\)\s+"
            r"(-?[0-9.eE+\-]+)",
            setup_text,
            re.IGNORECASE
        )

        if values:

            values = [
                float(x)
                for x in values
            ]

            result["wns_setup_ns"] = min(values)

            negative = [
                x for x in values
                if x < 0
            ]

            result["tns_setup_ns"] = (
                sum(negative)
                if negative
                else 0.0
            )

    if result["wns_hold_ns"] is None:

        values = re.findall(
            r"slack\s+\([^)]+\)\s+"
            r"(-?[0-9.eE+\-]+)",
            hold_text,
            re.IGNORECASE
        )

        if values:

            values = [
                float(x)
                for x in values
            ]

            result["wns_hold_ns"] = min(values)

    return result


# ================================================================
# Main
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

    metrics = {

        "run_tag": RUN_TAG,

        "array_size":
            int(os.environ.get("ARRAY_SIZE", 4)),

        "data_width":
            int(os.environ.get("DATA_WIDTH", 8)),

        "utilization":
            float(os.environ.get("UTIL", 50)),

        "clk_period_ns":
            float(os.environ.get("CLK_PERIOD", 5.0)),

        "num_cells": None,
        "num_nets": None,
        "num_pins": None,
        "num_buffers": None,

        "die_area_u2": None,
        "core_area_u2": None,

        "wirelength_u": None,
        "via_count": None,
        "congestion_overflow_pct": None,

        "wns_setup_ps": None,
        "tns_setup_ps": None,
        "wns_hold_ps": None
    }

    # ------------------------------------------------------------
    # Design statistics
    # ------------------------------------------------------------

    stats = extract_design_stats()

    for key in [
        "num_cells",
        "num_nets",
        "num_pins",
        "num_buffers"
    ]:
        metrics[key] = stats[key]

    # ------------------------------------------------------------
    # Area
    # ------------------------------------------------------------

    area = extract_area()

    metrics["die_area_u2"] = area["die_area_u2"]
    metrics["core_area_u2"] = area["core_area_u2"]

    # ------------------------------------------------------------
    # Wirelength
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Congestion
    # ------------------------------------------------------------

    congestion = extract_congestion()

    if congestion is not None:

        metrics["congestion_overflow_pct"] = (
            float(congestion)
        )

        print(
            "[OK] Routing overflow = "
            f"{congestion}"
        )

    else:

        print(
            "[WARNING] Congestion could not "
            "be extracted."
        )

    # ------------------------------------------------------------
    # Via count
    # ------------------------------------------------------------

    metrics["via_count"] = extract_vias()

    # ------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------

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

    # ------------------------------------------------------------
    # Final database
    # ------------------------------------------------------------

    odb_path = os.path.join(
        RUN_DIR,
        "final.odb"
    )

    if os.path.exists(odb_path):
        print("[INFO] final.odb exists.")
    else:
        print("[WARNING] final.odb missing.")

    # ------------------------------------------------------------
    # Validity
    # ------------------------------------------------------------

    metrics["wirelength_available"] = (
        metrics["wirelength_u"] is not None
    )

    metrics["congestion_available"] = (
        metrics["congestion_overflow_pct"] is not None
    )

    metrics["timing_available"] = (
        metrics["wns_setup_ps"] is not None
    )

    metrics["valid_run"] = (
        os.path.exists(odb_path)
        and metrics["wirelength_available"]
        and metrics["congestion_available"]
        and metrics["timing_available"]
    )

    # ------------------------------------------------------------
    # Save
    # ------------------------------------------------------------

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
        print(f"{key:30s}: {value}")

    print("=" * 70)


if __name__ == "__main__":
    extract_features()
