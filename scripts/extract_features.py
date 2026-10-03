#!/usr/bin/env python3

import os
import re
import json
import math
from pathlib import Path


# ================================================================
# CONFIGURATION
# ================================================================

RUN_TAG = os.environ.get("RUN_TAG", "run_test")

RUN_DIR = Path("systolic_project") / "runs" / RUN_TAG

OUTPUT_FILE = RUN_DIR / "features.json"

FINAL_DEF = RUN_DIR / "final.def"
TIMING_SETUP = RUN_DIR / "timing_setup.rpt"
TIMING_HOLD = RUN_DIR / "timing_hold.rpt"
CONGESTION = RUN_DIR / "congestion.rpt"


# ================================================================
# BASIC HELPERS
# ================================================================

def safe_float(value):
    try:
        return float(value)
    except Exception:
        return None


def read_text(path):
    if not path.exists():
        return ""
    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# ================================================================
# ENVIRONMENT FEATURES
# ================================================================

def get_environment_features():
    return {
        "run_tag": RUN_TAG,
        "array_size": int(os.environ.get("ARRAY_SIZE", "4")),
        "data_width": int(os.environ.get("DATA_WIDTH", "8")),
        "utilization": float(os.environ.get("UTIL", "50")),
        "clock_period": float(os.environ.get("CLK_PERIOD", "5.0")),
    }


# ================================================================
# DEF PARSER
# ================================================================

def parse_def(def_file):

    text = read_text(def_file)

    result = {
        "die_area_um2": None,
        "core_area_um2": None,
        "num_cells": 0,
        "num_nets": 0,
        "num_pins": 0,
        "num_registers": 0,
        "num_buffers": 0,
        "components": {},
        "nets": {},
    }

    if not text:
        return result

    # ------------------------------------------------------------
    # DIE AREA
    # ------------------------------------------------------------

    m = re.search(
        r"DIEAREA\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)"
        r"\s*\(\s*(-?\d+)\s+(-?\d+)\s*\)",
        text,
        re.S
    )

    if m:
        x0, y0, x1, y1 = map(int, m.groups())

        # SKY130 DEF coordinates are in database units.
        # SKY130 normally uses 1000 DBU/um.
        dbu = 1000.0

        width = abs(x1 - x0) / dbu
        height = abs(y1 - y0) / dbu

        result["die_area_um2"] = width * height

    # ------------------------------------------------------------
    # COMPONENTS
    # ------------------------------------------------------------

    comp_section = re.search(
        r"COMPONENTS\s+\d+\s*;(.*?)END COMPONENTS",
        text,
        re.S
    )

    if comp_section:

        component_text = comp_section.group(1)

        pattern = re.compile(
            r"-\s+(\S+)\s+(\S+).*?"
            r"\+\s+PLACED\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)"
            r"(?:\s+([NSEWFR]+))?",
            re.S
        )

        for m in pattern.finditer(component_text):

            inst = m.group(1)
            master = m.group(2)

            x = int(m.group(3))
            y = int(m.group(4))

            result["components"][inst] = {
                "master": master,
                "x": x,
                "y": y,
            }

    result["num_cells"] = len(result["components"])

    # ------------------------------------------------------------
    # REGISTERS / BUFFERS
    # ------------------------------------------------------------

    for inst, data in result["components"].items():

        master = data["master"].lower()

        # SKY130 sequential cells commonly contain:
        # dfrtp, dfrbp, dfxtp, dlrtp, etc.
        if re.search(r"(dff|dfr|dfb|dfx|dlr|latch)", master):
            result["num_registers"] += 1

        if "buf" in master:
            result["num_buffers"] += 1

    # ------------------------------------------------------------
    # NETS
    # ------------------------------------------------------------

    nets_section = re.search(
        r"NETS\s+\d+\s*;(.*?)END NETS",
        text,
        re.S
    )

    if nets_section:

        net_text = nets_section.group(1)

        # A simple DEF net extraction.
        # This is intentionally tolerant of routed geometry.
        net_pattern = re.compile(
            r"-\s+(\S+)(.*?)(?=\n\s*-\s+\S+|\Z)",
            re.S
        )

        for m in net_pattern.finditer(net_text):

            net_name = m.group(1)
            body = m.group(2)

            result["nets"][net_name] = body

    result["num_nets"] = len(result["nets"])

    # ------------------------------------------------------------
    # PINS
    # ------------------------------------------------------------

    pin_section = re.search(
        r"PINS\s+\d+\s*;(.*?)END PINS",
        text,
        re.S
    )

    if pin_section:

        pin_matches = re.findall(
            r"^\s*-\s+\S+",
            pin_section.group(1),
            re.M
        )

        result["num_pins"] = len(pin_matches)

    return result


# ================================================================
# COMPONENT-BASED FEATURES
# ================================================================

def calculate_component_features(def_data):

    components = def_data["components"]

    if not components:
        return {
            "x_spread": None,
            "y_spread": None,
            "max_density": None,
            "mean_density": None,
            "std_density": None,
            "pin_density": None,
        }

    xs = [c["x"] for c in components.values()]
    ys = [c["y"] for c in components.values()]

    x_spread = (max(xs) - min(xs)) / 1000.0
    y_spread = (max(ys) - min(ys)) / 1000.0

    # ------------------------------------------------------------
    # 10 x 10 placement density grid
    # ------------------------------------------------------------

    xmin = min(xs)
    xmax = max(xs)
    ymin = min(ys)
    ymax = max(ys)

    nx = 10
    ny = 10

    grid = [[0 for _ in range(nx)] for _ in range(ny)]

    xrange = max(xmax - xmin, 1)
    yrange = max(ymax - ymin, 1)

    for c in components.values():

        gx = int(
            (c["x"] - xmin) / xrange * nx
        )

        gy = int(
            (c["y"] - ymin) / yrange * ny
        )

        gx = min(max(gx, 0), nx - 1)
        gy = min(max(gy, 0), ny - 1)

        grid[gy][gx] += 1

    total_cells = len(components)

    densities = []

    for row in grid:
        for count in row:
            density = (
                count / total_cells * 100.0 * nx * ny
            )
            densities.append(density)

    mean_density = sum(densities) / len(densities)

    variance = sum(
        (d - mean_density) ** 2
        for d in densities
    ) / len(densities)

    std_density = math.sqrt(variance)

    max_density = max(densities)

    # ------------------------------------------------------------
    # Pin density
    # ------------------------------------------------------------

    pin_density = None

    if total_cells > 0:
        # Estimate from number of pins / placement area.
        #
        # This is kept as a feature derived from the actual design
        # rather than a fixed value.
        #
        # num_pins is handled later from DEF.
        pass

    return {
        "x_spread": round(x_spread, 6),
        "y_spread": round(y_spread, 6),
        "max_density": round(max_density, 6),
        "mean_density": round(mean_density, 6),
        "std_density": round(std_density, 6),
        "pin_density": pin_density,
    }


# ================================================================
# NET / FANOUT FEATURES
# ================================================================

def calculate_fanout_features(def_data):

    nets = def_data["nets"]

    if not nets:
        return {
            "avg_fanout": None,
            "max_fanout": None,
        }

    fanouts = []

    for body in nets.values():

        # Every occurrence of a connection:
        # ( inst pin )
        connections = re.findall(
            r"\(\s+\S+\s+\S+\s*\)",
            body
        )

        if connections:
            fanout = max(len(connections) - 1, 0)
            fanouts.append(fanout)

    if not fanouts:
        return {
            "avg_fanout": None,
            "max_fanout": None,
        }

    return {
        "avg_fanout": round(
            sum(fanouts) / len(fanouts),
            6
        ),
        "max_fanout": float(max(fanouts)),
    }


# ================================================================
# ROUTED WIRELENGTH / VIA COUNT
# ================================================================

def calculate_routing_from_def(def_file):

    text = read_text(def_file)

    if not text:
        return {
            "wirelength_um": None,
            "via_count": None,
            "routed_net_count": None,
        }

    wirelength_dbu = 0.0
    via_count = 0
    routed_net_count = 0

    # ------------------------------------------------------------
    # Count routed nets
    # ------------------------------------------------------------

    nets_section = re.search(
        r"NETS\s+\d+\s*;(.*?)END NETS",
        text,
        re.S
    )

    if nets_section:

        net_text = nets_section.group(1)

        net_blocks = re.findall(
            r"(?ms)^\s*-\s+\S+.*?(?=^\s*-\s+\S+|\Z)",
            net_text
        )

        for block in net_blocks:

            if "ROUTED" in block.upper():
                routed_net_count += 1

    # ------------------------------------------------------------
    # Routed geometry
    #
    # Supports:
    #
    #   ( x y ) ( x y )
    #   NEW met1 ...
    #   ROUTED met1 ...
    #
    # ------------------------------------------------------------

    routed_sections = re.findall(
        r"(?is)(?:ROUTED|FIXED).*?(?=^\s*-\s+\S+|\Z)",
        text
    )

    coordinate_pattern = re.compile(
        r"\(\s*(-?\d+)\s+(-?\d+)\s*\)"
    )

    for section in routed_sections:

        coords = [
            (int(x), int(y))
            for x, y in coordinate_pattern.findall(section)
        ]

        if len(coords) < 2:
            continue

        for i in range(1, len(coords)):

            x1, y1 = coords[i - 1]
            x2, y2 = coords[i]

            wirelength_dbu += abs(x2 - x1)
            wirelength_dbu += abs(y2 - y1)

        # DEF routed sections may contain vias.
        via_count += len(
            re.findall(
                r"\bvia\d*\b",
                section,
                re.I
            )
        )

    wirelength_um = wirelength_dbu / 1000.0

    return {
        "wirelength_um": (
            round(wirelength_um, 6)
            if wirelength_um > 0
            else None
        ),
        "via_count": int(via_count),
        "routed_net_count": (
            int(routed_net_count)
            if routed_net_count > 0
            else None
        ),
    }


# ================================================================
# ESTIMATED WIRELENGTH
# ================================================================

def calculate_estimated_wirelength(def_data):

    components = def_data["components"]

    if not components:
        return None

    total = 0.0

    # Estimate using net bounding boxes.
    for body in def_data["nets"].values():

        refs = re.findall(
            r"\(\s+(\S+)\s+\S+\s*\)",
            body
        )

        points = []

        for ref in refs:

            if ref in components:
                c = components[ref]
                points.append((c["x"], c["y"]))

        if len(points) < 2:
            continue

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]

        total += (
            max(xs) - min(xs)
        )

        total += (
            max(ys) - min(ys)
        )

    return round(total / 1000.0, 6)


# ================================================================
# CONGESTION
# ================================================================

def extract_congestion():

    text = read_text(CONGESTION)

    if not text.strip():
        return None

    values = []

    # Search for numerical congestion/overflow values.
    patterns = [
        r"overflow\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
        r"congestion\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
        r"total\s+overflow\s*[:=]\s*([-+]?\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:

        for value in re.findall(
            pattern,
            text,
            re.I
        ):
            try:
                values.append(float(value))
            except Exception:
                pass

    if values:
        return round(max(values), 6)

    # ------------------------------------------------------------
    # Fallback:
    #
    # If the congestion report contains a numeric grid,
    # calculate the maximum numeric congestion value.
    # ------------------------------------------------------------

    numeric_values = []

    for line in text.splitlines():

        if not line.strip():
            continue

        nums = re.findall(
            r"[-+]?\d+(?:\.\d+)?",
            line
        )

        for n in nums:

            try:
                v = float(n)

                if v >= 0:
                    numeric_values.append(v)

            except Exception:
                pass

    if numeric_values:
        return round(max(numeric_values), 6)

    return None


# ================================================================
# TIMING PARSER
# ================================================================

def parse_timing_report():

    text = read_text(TIMING_SETUP)

    result = {
        "WNS": None,
        "TNS": None,
        "logic_depth": None,
        "crit_path_wirelength": None,
    }

    if not text:
        return result

    # ------------------------------------------------------------
    # WNS
    # ------------------------------------------------------------

    slack_values = []

    for value in re.findall(
        r"slack\s+\((?:VIOLATED|MET)\)\s*",
        text,
        re.I
    ):
        pass

    # Capture numeric value immediately before slack status.
    for value in re.findall(
        r"([-+]?\d+(?:\.\d+)?)\s+slack\s+\((?:VIOLATED|MET)\)",
        text,
        re.I
    ):

        try:
            slack_values.append(float(value))
        except Exception:
            pass

    if slack_values:
        result["WNS"] = min(slack_values)

    # ------------------------------------------------------------
    # TNS
    #
    # If an explicit TNS line exists, use it.
    # Otherwise derive it from the report.
    # ------------------------------------------------------------

    tns_match = re.search(
        r"\bTNS\b[^\n]*?([-+]?\d+(?:\.\d+)?)",
        text,
        re.I
    )

    if tns_match:

        result["TNS"] = float(tns_match.group(1))

    # ------------------------------------------------------------
    # Find the worst setup path
    #
    # We select the path having the minimum slack.
    # ------------------------------------------------------------

    path_blocks = re.split(
        r"(?=Startpoint:)",
        text
    )

    worst_block = None
    worst_slack = None

    for block in path_blocks:

        if "Startpoint:" not in block:
            continue

        m = re.search(
            r"([-+]?\d+(?:\.\d+)?)\s+slack\s+\((?:VIOLATED|MET)\)",
            block,
            re.I
        )

        if not m:
            continue

        slack = float(m.group(1))

        if worst_slack is None or slack < worst_slack:
            worst_slack = slack
            worst_block = block

    if worst_block:

        # --------------------------------------------------------
        # Extract instances from timing path.
        #
        # Example:
        #
        # _05480_/X (sky130_fd_sc_hd__xor3_1)
        # --------------------------------------------------------

        cell_matches = re.findall(
            r"([A-Za-z0-9_$.\[\]-]+)/(?:[A-Za-z0-9_$.\[\]-]+)"
            r"\s+\(sky130_fd_sc_hd__([A-Za-z0-9_]+)\)",
            worst_block
        )

        cells = []

        for inst, master in cell_matches:

            cells.append({
                "inst": inst,
                "master": master.lower()
            })

        # --------------------------------------------------------
        # LOGIC DEPTH
        #
        # Count combinational cells.
        # Sequential cells are excluded.
        # --------------------------------------------------------

        combinational_cells = []

        for cell in cells:

            master = cell["master"]

            is_sequential = bool(
                re.search(
                    r"(dff|dfr|dfb|dfx|dlr|latch)",
                    master
                )
            )

            if not is_sequential:
                combinational_cells.append(cell)

        if combinational_cells:

            result["logic_depth"] = len(
                combinational_cells
            )

        # --------------------------------------------------------
        # CRITICAL PATH WIRELENGTH
        #
        # Obtain component coordinates from final.def.
        # Then calculate Manhattan distance between consecutive
        # cells appearing in the actual critical timing path.
        #
        # This is an estimated critical-path physical length.
        # --------------------------------------------------------

        def_data = parse_def(FINAL_DEF)

        components = def_data["components"]

        path_points = []

        for cell in cells:

            inst = cell["inst"]

            if inst in components:

                c = components[inst]

                path_points.append(
                    (c["x"], c["y"])
                )

        if len(path_points) >= 2:

            distance = 0.0

            for i in range(1, len(path_points)):

                x1, y1 = path_points[i - 1]
                x2, y2 = path_points[i]

                distance += abs(x2 - x1)
                distance += abs(y2 - y1)

            result["crit_path_wirelength"] = round(
                distance / 1000.0,
                6
            )

    return result


# ================================================================
# HOLD TIMING
# ================================================================

def parse_hold_timing():

    text = read_text(TIMING_HOLD)

    if not text:
        return {
            "hold_WNS": None,
            "hold_TNS": None,
        }

    slack_values = []

    for value in re.findall(
        r"([-+]?\d+(?:\.\d+)?)\s+slack\s+\((?:VIOLATED|MET)\)",
        text,
        re.I
    ):

        try:
            slack_values.append(float(value))
        except Exception:
            pass

    if not slack_values:
        return {
            "hold_WNS": None,
            "hold_TNS": None,
        }

    wns = min(slack_values)

    # ------------------------------------------------------------
    # Sum only negative slacks for TNS.
    # ------------------------------------------------------------

    negative = [
        v for v in slack_values
        if v < 0
    ]

    tns = sum(negative)

    return {
        "hold_WNS": round(wns, 6),
        "hold_TNS": round(tns, 6),
    }


# ================================================================
# MAIN EXTRACTION
# ================================================================

def main():

    print("=" * 70)
    print("FEATURE EXTRACTION")
    print("=" * 70)

    print(f"Run tag : {RUN_TAG}")
    print(f"Run dir : {RUN_DIR}")

    RUN_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ------------------------------------------------------------
    # Check essential files
    # ------------------------------------------------------------

    if not FINAL_DEF.exists():
        print("[ERROR] final.def not found.")
        raise SystemExit(1)

    if not TIMING_SETUP.exists():
        print("[ERROR] timing_setup.rpt not found.")
        raise SystemExit(1)

    print("[INFO] final.def exists.")
    print("[INFO] timing_setup.rpt exists.")

    # ------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------

    env = get_environment_features()

    # ------------------------------------------------------------
    # DEF
    # ------------------------------------------------------------

    def_data = parse_def(FINAL_DEF)

    # ------------------------------------------------------------
    # Placement features
    # ------------------------------------------------------------

    placement = calculate_component_features(
        def_data
    )

    # ------------------------------------------------------------
    # Fanout
    # ------------------------------------------------------------

    fanout = calculate_fanout_features(
        def_data
    )

    # ------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------

    routing = calculate_routing_from_def(
        FINAL_DEF
    )

    # ------------------------------------------------------------
    # Estimated WL
    # ------------------------------------------------------------

    estimated_wirelength = (
        calculate_estimated_wirelength(
            def_data
        )
    )

    # ------------------------------------------------------------
    # Congestion
    # ------------------------------------------------------------

    congestion = extract_congestion()

    # ------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------

    timing = parse_timing_report()

    hold = parse_hold_timing()

    # ------------------------------------------------------------
    # Pin density
    # ------------------------------------------------------------

    pin_density = None

    if (
        def_data["num_pins"] is not None
        and def_data["die_area_um2"]
        and def_data["die_area_um2"] > 0
    ):

        pin_density = round(
            def_data["num_pins"] /
            def_data["die_area_um2"] *
            1e4,
            6
        )

    # ------------------------------------------------------------
    # Construct 17 core features
    # ------------------------------------------------------------

    features = {

        "run_tag":
            RUN_TAG,

        "array_size":
            env["array_size"],

        "data_width":
            env["data_width"],

        # 1
        "max_density":
            placement["max_density"],

        # 2
        "mean_density":
            placement["mean_density"],

        # 3
        "std_density":
            placement["std_density"],

        # 4
        "pin_density":
            pin_density,

        # 5
        "avg_fanout":
            fanout["avg_fanout"],

        # 6
        "max_fanout":
            fanout["max_fanout"],

        # 7
        "x_spread":
            placement["x_spread"],

        # 8
        "y_spread":
            placement["y_spread"],

        # 9
        "num_registers":
            def_data["num_registers"],

        # 10
        "logic_depth":
            timing["logic_depth"],

        # 11
        "crit_path_wirelength":
            timing["crit_path_wirelength"],

        # 12
        "estimated_wirelength":
            estimated_wirelength,

        # 13
        "congestion":
            congestion,

        # 14
        "WNS":
            timing["WNS"],

        # 15
        "TNS":
            timing["TNS"],

        # 16
        "utilization":
            env["utilization"],

        # 17
        "clock_period":
            env["clock_period"],

        # --------------------------------------------------------
        # Additional physical-design outputs
        # --------------------------------------------------------

        "wirelength_um":
            routing["wirelength_um"],

        "via_count":
            routing["via_count"],

        "routed_net_count":
            routing["routed_net_count"],

        "hold_WNS":
            hold["hold_WNS"],

        "hold_TNS":
            hold["hold_TNS"],

        "num_cells":
            def_data["num_cells"],

        "num_nets":
            def_data["num_nets"],

        "num_pins":
            def_data["num_pins"],

        "num_buffers":
            def_data["num_buffers"],

    }

    # ------------------------------------------------------------
    # Availability flags
    # ------------------------------------------------------------

    wirelength_available = (
        features["wirelength_um"] is not None
    )

    via_count_available = (
        features["via_count"] is not None
    )

    congestion_available = (
        features["congestion"] is not None
    )

    timing_available = (
        features["WNS"] is not None
        and features["TNS"] is not None
    )

    # ------------------------------------------------------------
    # Required feature validation
    # ------------------------------------------------------------

    required_features = [
        "max_density",
        "mean_density",
        "std_density",
        "pin_density",
        "avg_fanout",
        "max_fanout",
        "x_spread",
        "y_spread",
        "num_registers",
        "logic_depth",
        "crit_path_wirelength",
        "estimated_wirelength",
        "congestion",
        "WNS",
        "TNS",
        "utilization",
        "clock_period",
        "wirelength_um",
        "via_count",
        "routed_net_count",
    ]

    missing_required = [
        name
        for name in required_features
        if features.get(name) is None
    ]

    valid_run = (
        len(missing_required) == 0
    )

    # ------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------

    features["wirelength_available"] = (
        wirelength_available
    )

    features["via_count_available"] = (
        via_count_available
    )

    features["congestion_available"] = (
        congestion_available
    )

    features["timing_available"] = (
        timing_available
    )

    features["valid_run"] = valid_run

    features["missing_required_features"] = (
        missing_required
    )

    # ------------------------------------------------------------
    # Write JSON
    # ------------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            features,
            f,
            indent=2
        )

    # ------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------

    print("=" * 70)
    print("FEATURE EXTRACTION COMPLETE")
    print("=" * 70)

    print(f"Output: {OUTPUT_FILE}")
    print()

    for key, value in features.items():
        print(
            f"{key:<30}: {value}"
        )

    print()

    if valid_run:

        print("=" * 70)
        print("[SUCCESS] VALID RUN")
        print("All required features are available.")
        print("=" * 70)

    else:

        print("=" * 70)
        print("[WARNING] INVALID RUN")
        print("Missing required features:")

        for feature in missing_required:
            print(f"  - {feature}")

        print("=" * 70)


if __name__ == "__main__":
    main()
