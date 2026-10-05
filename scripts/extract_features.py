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

# Official setup timing summary files
WNS_SETUP = RUN_DIR / "wns_setup.rpt"
TNS_SETUP = RUN_DIR / "tns_setup.rpt"

CONGESTION = RUN_DIR / "congestion.rpt"
GLOBAL_ROUTE_REPORT = RUN_DIR / "global_route.rpt"
OPENROAD_LOG = RUN_DIR / "openroad_log.txt"

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
        if re.search(
            r"(dff|dfr|dfb|dfx|dlr|latch)",
            master
        ):
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

    grid = [
        [0 for _ in range(nx)]
        for _ in range(ny)
    ]

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
                count / total_cells
                * 100.0
                * nx
                * ny
            )

            densities.append(density)

    mean_density = (
        sum(densities) /
        len(densities)
    )

    variance = (
        sum(
            (d - mean_density) ** 2
            for d in densities
        )
        / len(densities)
    )

    std_density = math.sqrt(variance)

    max_density = max(densities)

    return {
        "x_spread": round(x_spread, 6),
        "y_spread": round(y_spread, 6),
        "max_density": round(max_density, 6),
        "mean_density": round(mean_density, 6),
        "std_density": round(std_density, 6),
        "pin_density": None,
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

    for net_name, body in nets.items():

        # --------------------------------------------------------
        # Exclude obvious power / ground nets.
        # --------------------------------------------------------

        name_upper = net_name.upper()

        power_ground_names = {
            "VDD",
            "VSS",
            "VPWR",
            "VGND",
            "VCCD",
            "VSSD",
            "VCCA",
            "VSSA",
        }

        if (
            name_upper in power_ground_names
            or name_upper.startswith("VDD")
            or name_upper.startswith("VSS")
            or name_upper.startswith("VPWR")
            or name_upper.startswith("VGND")
            or name_upper.startswith("VCCD")
            or name_upper.startswith("VSSD")
            or name_upper.startswith("VCCA")
            or name_upper.startswith("VSSA")
        ):
            continue

        # --------------------------------------------------------
        # Every occurrence of:
        #
        #     ( inst pin )
        #
        # represents a DEF net connection.
        # --------------------------------------------------------

        connections = re.findall(
            r"\(\s+\S+\s+\S+\s*\)",
            body
        )

        if connections:

            fanout = max(
                len(connections) - 1,
                0
            )

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
        "max_fanout": float(
            max(fanouts)
        ),
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
            r"(?ms)^\s*-\s+\S+.*?"
            r"(?=^\s*-\s+\S+|\Z)",
            net_text
        )

        for block in net_blocks:

            if "ROUTED" in block.upper():
                routed_net_count += 1

    # ------------------------------------------------------------
    # Routed geometry
    # ------------------------------------------------------------

    routed_sections = re.findall(
        r"(?is)(?:ROUTED|FIXED).*?"
        r"(?=^\s*-\s+\S+|\Z)",
        text
    )

    coordinate_pattern = re.compile(
        r"\(\s*(-?\d+)\s+(-?\d+)\s*\)"
    )

    for section in routed_sections:

        coords = [
            (int(x), int(y))
            for x, y
            in coordinate_pattern.findall(section)
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

    wirelength_um = (
        wirelength_dbu / 1000.0
    )

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

                points.append(
                    (
                        c["x"],
                        c["y"]
                    )
                )

        if len(points) < 2:
            continue

        xs = [
            p[0]
            for p in points
        ]

        ys = [
            p[1]
            for p in points
        ]

        total += (
            max(xs) - min(xs)
        )

        total += (
            max(ys) - min(ys)
        )

    return round(
        total / 1000.0,
        6
    )


# ================================================================
# CONGESTION
# ================================================================

def extract_congestion():
    """
    Extract a scalar congestion metric.

    Priority:
        1. Numeric congestion value from global_route.rpt
        2. Numeric congestion value from congestion.rpt
        3. Explicit zero-overflow statement from global_route.rpt
        4. Explicit zero-overflow statement from openroad_log.txt

    IMPORTANT:
        An empty congestion.rpt by itself does NOT mean congestion = 0.

        It is converted to 0.0 only when another routing artifact
        explicitly confirms that no routing overflow / overflowing
        GCells were reported.

    Metric interpretation:
        congestion = routing overflow / congestion value.
        Therefore a confirmed zero-overflow run is represented as 0.0.
    """

    # --------------------------------------------------------------
    # Helper: parse numeric congestion values
    # --------------------------------------------------------------

    def parse_percentage(text):
        """
        Look for percentage values associated with congestion,
        overflow, usage, or routing.

        Returns the most appropriate numeric value or None.
        """

        if not text:
            return None

        # ----------------------------------------------------------
        # 1. Total row
        #
        # Example:
        # Total  ...  85.4% ...
        # ----------------------------------------------------------

        total_pattern = re.compile(
            r"^\s*Total\b.*?"
            r"([-+]?\d+(?:\.\d+)?)\s*%",
            re.IGNORECASE | re.MULTILINE
        )

        match = total_pattern.search(text)

        if match:
            try:
                value = float(match.group(1))

                if math.isfinite(value) and 0.0 <= value <= 1000.0:
                    return round(value, 6)

            except Exception:
                pass

        # ----------------------------------------------------------
        # 2. Explicit congestion percentage
        # ----------------------------------------------------------

        congestion_patterns = [

            r"(?:congestion|overflow)"
            r"[^\n]{0,100}?"
            r"([-+]?\d+(?:\.\d+)?)\s*%",

            r"([-+]?\d+(?:\.\d+)?)\s*%"
            r"[^\n]{0,100}?"
            r"(?:congestion|overflow)",

        ]

        for pattern in congestion_patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:

                try:

                    value = float(
                        match.group(1)
                    )

                    if (
                        math.isfinite(value)
                        and 0.0 <= value <= 1000.0
                    ):
                        return round(
                            value,
                            6
                        )

                except Exception:
                    pass

        return None

    # --------------------------------------------------------------
    # 1. global_route.rpt
    # --------------------------------------------------------------

    if GLOBAL_ROUTE_REPORT.exists():

        try:

            text = GLOBAL_ROUTE_REPORT.read_text(
                errors="ignore"
            )

            if text.strip():

                # --------------------------------------------------
                # First try numeric congestion information.
                # --------------------------------------------------

                value = parse_percentage(text)

                if value is not None:

                    print(
                        "[INFO] Congestion extracted from "
                        "global_route.rpt: "
                        f"{value}"
                    )

                    return value

                # --------------------------------------------------
                # IMPORTANT:
                # Your TCL creates global_route.rpt with this
                # message when congestion.rpt is absent because
                # there were no overflowing GCells.
                # --------------------------------------------------

                zero_overflow_patterns = [

                    r"no\s+overflowing\s+gcell",

                    r"no\s+overflowing\s+gcells",

                    r"no\s+overflow",

                    r"zero\s+overflow",

                    r"overflow\s*[:=]\s*0(?:\.0+)?",

                    r"total\s+overflow\s*[:=]\s*0(?:\.0+)?",

                    r"routing\s+overflow\s*[:=]\s*0(?:\.0+)?",

                ]

                for pattern in zero_overflow_patterns:

                    if re.search(
                        pattern,
                        text,
                        re.IGNORECASE
                    ):

                        print(
                            "[INFO] Global routing report "
                            "explicitly confirms zero "
                            "routing overflow."
                        )

                        print(
                            "[INFO] Congestion set to 0.0"
                        )

                        return 0.0

        except Exception as exc:

            print(
                "[WARNING] Failed to parse "
                f"global_route.rpt: {exc}"
            )

    # --------------------------------------------------------------
    # 2. congestion.rpt
    # --------------------------------------------------------------

    if CONGESTION.exists():

        try:

            text = CONGESTION.read_text(
                errors="ignore"
            )

            if text.strip():

                value = parse_percentage(text)

                if value is not None:

                    print(
                        "[INFO] Congestion extracted from "
                        "congestion.rpt: "
                        f"{value}"
                    )

                    return value

                # --------------------------------------------------
                # Look for explicit zero overflow without '%'.
                # --------------------------------------------------

                zero_overflow_patterns = [

                    r"overflow\s*[:=]\s*0(?:\.0+)?\b",

                    r"total\s+overflow\s*[:=]\s*0(?:\.0+)?\b",

                    r"routing\s+overflow\s*[:=]\s*0(?:\.0+)?\b",

                    r"no\s+overflow",

                    r"no\s+overflowing\s+gcell",

                    r"no\s+overflowing\s+gcells",

                ]

                for pattern in zero_overflow_patterns:

                    if re.search(
                        pattern,
                        text,
                        re.IGNORECASE
                    ):

                        print(
                            "[INFO] congestion.rpt "
                            "explicitly confirms zero "
                            "routing overflow."
                        )

                        return 0.0

        except Exception as exc:

            print(
                "[WARNING] Failed to parse "
                f"congestion.rpt: {exc}"
            )

    # --------------------------------------------------------------
    # 3. OpenROAD log fallback
    # --------------------------------------------------------------

    if OPENROAD_LOG.exists():

        try:

            text = OPENROAD_LOG.read_text(
                errors="ignore"
            )

            if text.strip():

                # --------------------------------------------------
                # First look for explicit numeric congestion.
                # --------------------------------------------------

                value = parse_percentage(text)

                if value is not None:

                    print(
                        "[INFO] Congestion extracted from "
                        "openroad_log.txt: "
                        f"{value}"
                    )

                    return value

                # --------------------------------------------------
                # Then look for explicit zero-overflow evidence.
                # --------------------------------------------------

                zero_overflow_patterns = [

                    r"no\s+overflowing\s+gcell",

                    r"no\s+overflowing\s+gcells",

                    r"no\s+routing\s+overflow",

                    r"routing\s+overflow\s*[:=]\s*0(?:\.0+)?",

                    r"total\s+overflow\s*[:=]\s*0(?:\.0+)?",

                    r"\boverflow\s*[:=]\s*0(?:\.0+)?\b",

                    r"\boverflow\s*=\s*0(?:\.0+)?\b",

                ]

                for pattern in zero_overflow_patterns:

                    if re.search(
                        pattern,
                        text,
                        re.IGNORECASE
                    ):

                        print(
                            "[INFO] OpenROAD log "
                            "confirms zero routing overflow."
                        )

                        print(
                            "[INFO] Congestion set to 0.0"
                        )

                        return 0.0

        except Exception as exc:

            print(
                "[WARNING] Failed to parse "
                f"openroad_log.txt: {exc}"
            )

    # --------------------------------------------------------------
    # 4. No reliable congestion information
    # --------------------------------------------------------------

    print(
        "[WARNING] No reliable congestion information found."
    )

    print(
        "[WARNING] congestion remains None."
    )

    return None

# ================================================================
# TIMING SCALAR REPORT
# ================================================================

def extract_scalar_report(path, metric_name):

    """
    Extract a scalar metric from a simple report such as:

        wns -21.28
        tns -2649.80

    Returns None if the file does not exist or
    the metric cannot be parsed.
    """

    if not path.exists():

        print(
            f"[WARN] {path.name} not found."
        )

        return None

    try:

        text = path.read_text(
            errors="ignore"
        ).strip()

    except Exception as e:

        print(
            f"[WARN] Could not read {path}: {e}"
        )

        return None

    if not text:

        print(
            f"[WARN] {path.name} is empty."
        )

        return None

    pattern = (
        rf"\b{re.escape(metric_name)}\b"
        rf"\s*[:=]?\s*"
        rf"(-?\d+(?:\.\d+)?"
        rf"(?:[eE][+-]?\d+)?)"
    )

    match = re.search(
        pattern,
        text,
        re.IGNORECASE
    )

    if match:

        value = float(
            match.group(1)
        )

        print(
            f"[INFO] {metric_name.upper()} "
            f"extracted from {path.name}: {value}"
        )

        return value

    print(
        f"[WARN] Could not find "
        f"{metric_name} in {path.name}"
    )

    return None


# ================================================================
# TIMING PARSER
# ================================================================

def parse_timing_report():

    text = read_text(
        TIMING_SETUP
    )

    result = {
        "WNS": None,
        "TNS": None,
        "logic_depth": None,
        "crit_path_wirelength": None,
    }

    if not text.strip():

        print(
            "[WARNING] timing_setup.rpt is empty."
        )

        return result

    # ------------------------------------------------------------
    # WNS
    # ------------------------------------------------------------

    slack_values = []

    slack_pattern = re.compile(
        r"([-+]?\d+(?:\.\d+)?)"
        r"\s+slack\s+"
        r"\((?:VIOLATED|MET)\)",
        re.I
    )

    for match in slack_pattern.finditer(text):

        try:

            slack_values.append(
                float(match.group(1))
            )

        except Exception:
            pass

    # ------------------------------------------------------------
    # Additional slack formats
    # ------------------------------------------------------------

    if not slack_values:

        alternate_patterns = [

            r"\bslack\b\s*[:=]\s*"
            r"([-+]?\d+(?:\.\d+)?)",

            r"\bslack\b.*?"
            r"([-+]?\d+(?:\.\d+)?)",
        ]

        for pattern in alternate_patterns:

            for value in re.findall(
                pattern,
                text,
                re.I
            ):

                try:

                    slack_values.append(
                        float(value)
                    )

                except Exception:
                    pass

            if slack_values:
                break

    # ------------------------------------------------------------
    # WNS = minimum slack
    # ------------------------------------------------------------

    if slack_values:

        result["WNS"] = round(
            min(slack_values),
            6
        )

        print(
            f"[INFO] Setup WNS extracted: "
            f"{result['WNS']}"
        )

    # ------------------------------------------------------------
    # TNS
    #
    # This remains as a fallback only.
    # The authoritative tns_setup.rpt is read in main().
    # ------------------------------------------------------------

    explicit_tns_patterns = [

        r"\bTNS\b\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",

        r"\bTNS\b\s+"
        r"([-+]?\d+(?:\.\d+)?)",

        r"\btotal\s+negative\s+slack\b"
        r"\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",

        r"\btotal\s+negative\s+slack\b"
        r"[^\n]*?"
        r"([-+]?\d+(?:\.\d+)?)",

        r"\bnegative\s+slack\b"
        r"\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",
    ]

    explicit_tns = None

    for pattern in explicit_tns_patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            try:

                explicit_tns = float(
                    match.group(1)
                )

                if math.isfinite(
                    explicit_tns
                ):
                    break

            except Exception:
                pass

    if explicit_tns is not None:

        result["TNS"] = round(
            explicit_tns,
            6
        )

        print(
            f"[INFO] Setup TNS extracted "
            f"explicitly: {result['TNS']}"
        )

    elif slack_values:

        negative_slacks = [
            value
            for value in slack_values
            if value < 0
        ]

        if negative_slacks:

            result["TNS"] = round(
                sum(negative_slacks),
                6
            )

        else:

            result["TNS"] = 0.0

        print(
            f"[INFO] Setup TNS derived "
            f"from reported slacks: "
            f"{result['TNS']}"
        )

    # ------------------------------------------------------------
    # Find worst setup path
    # ------------------------------------------------------------

    path_blocks = re.split(
        r"(?=Startpoint:)",
        text,
        flags=re.I
    )

    worst_block = None
    worst_slack = None

    for block in path_blocks:

        if not re.search(
            r"Startpoint:",
            block,
            re.I
        ):
            continue

        matches = slack_pattern.findall(
            block
        )

        if not matches:
            continue

        try:

            slack = float(
                matches[-1]
            )

        except Exception:

            continue

        if (
            worst_slack is None
            or slack < worst_slack
        ):

            worst_slack = slack
            worst_block = block

    # ------------------------------------------------------------
    # If no Startpoint blocks were found,
    # use whole report.
    # ------------------------------------------------------------

    if (
        worst_block is None
        and slack_values
    ):

        worst_block = text

        worst_slack = min(
            slack_values
        )

    # ------------------------------------------------------------
    # Critical path information
    # ------------------------------------------------------------

    if worst_block:

        # --------------------------------------------------------
        # Extract cells
        # --------------------------------------------------------

        cell_matches = re.findall(
            r"([A-Za-z0-9_$.\[\]/-]+)"
            r"/[A-Za-z0-9_$.\[\]-]+"
            r"\s+\("
            r"(?:sky130_fd_sc_hd__)?"
            r"([A-Za-z0-9_]+)"
            r"\)",
            worst_block
        )

        cells = []

        for inst, master in cell_matches:

            cells.append(
                {
                    "inst": inst,
                    "master": master.lower(),
                }
            )

        # --------------------------------------------------------
        # LOGIC DEPTH
        # --------------------------------------------------------

        combinational_cells = []

        for cell in cells:

            master = cell["master"]

            is_sequential = bool(
                re.search(
                    r"(dff|dfr|dfb|dfx|dlr|latch)",
                    master,
                    re.I
                )
            )

            if not is_sequential:

                combinational_cells.append(
                    cell
                )

        if combinational_cells:

            result["logic_depth"] = len(
                combinational_cells
            )

        # --------------------------------------------------------
        # CRITICAL PATH WIRELENGTH
        # --------------------------------------------------------

        def_data = parse_def(
            FINAL_DEF
        )

        components = def_data[
            "components"
        ]

        path_points = []

        for cell in cells:

            inst = cell["inst"]

            if inst in components:

                c = components[inst]

                path_points.append(
                    (
                        c["x"],
                        c["y"]
                    )
                )

        if len(path_points) >= 2:

            distance = 0.0

            for i in range(
                1,
                len(path_points)
            ):

                x1, y1 = path_points[i - 1]
                x2, y2 = path_points[i]

                distance += abs(
                    x2 - x1
                )

                distance += abs(
                    y2 - y1
                )

            result[
                "crit_path_wirelength"
            ] = round(
                distance / 1000.0,
                6
            )

    return result


# ================================================================
# HOLD TIMING
# ================================================================

def parse_hold_timing():

    text = read_text(
        TIMING_HOLD
    )

    if not text:

        return {
            "hold_WNS": None,
            "hold_TNS": None,
        }

    slack_values = []

    for value in re.findall(
        r"([-+]?\d+(?:\.\d+)?)"
        r"\s+slack\s+"
        r"\((?:VIOLATED|MET)\)",
        text,
        re.I
    ):

        try:

            slack_values.append(
                float(value)
            )

        except Exception:
            pass

    if not slack_values:

        return {
            "hold_WNS": None,
            "hold_TNS": None,
        }

    wns = min(
        slack_values
    )

    negative = [
        v
        for v in slack_values
        if v < 0
    ]

    tns = sum(
        negative
    )

    return {
        "hold_WNS": round(
            wns,
            6
        ),
        "hold_TNS": round(
            tns,
            6
        ),
    }


# ================================================================
# MAIN EXTRACTION
# ================================================================

def main():

    print("=" * 70)
    print("FEATURE EXTRACTION")
    print("=" * 70)

    print(
        f"Run tag : {RUN_TAG}"
    )

    print(
        f"Run dir : {RUN_DIR}"
    )

    RUN_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    # ------------------------------------------------------------
    # Check essential files
    # ------------------------------------------------------------

    if not FINAL_DEF.exists():

        print(
            "[ERROR] final.def not found."
        )

        raise SystemExit(1)

    if not TIMING_SETUP.exists():

        print(
            "[ERROR] timing_setup.rpt not found."
        )

        raise SystemExit(1)

    print(
        "[INFO] final.def exists."
    )

    print(
        "[INFO] timing_setup.rpt exists."
    )

    # ------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------

    env = get_environment_features()

    # ------------------------------------------------------------
    # DEF
    # ------------------------------------------------------------

    def_data = parse_def(
        FINAL_DEF
    )

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

    # ------------------------------------------------------------
    # AUTHORITATIVE SETUP WNS / TNS
    # ------------------------------------------------------------
    #
    # timing_setup.rpt is used for:
    #   - logic depth
    #   - critical path wirelength
    #
    # Dedicated summary files are authoritative for:
    #   - WNS
    #   - TNS
    #
    # This means every run gets its own WNS/TNS values.
    # Nothing is hardcoded.
    # ------------------------------------------------------------

    setup_wns = extract_scalar_report(
        WNS_SETUP,
        "wns"
    )

    setup_tns = extract_scalar_report(
        TNS_SETUP,
        "tns"
    )

    if setup_wns is not None:

        timing["WNS"] = round(
            setup_wns,
            6
        )

    if setup_tns is not None:

        timing["TNS"] = round(
            setup_tns,
            6
        )

    # ------------------------------------------------------------
    # Hold timing
    # ------------------------------------------------------------

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
            def_data["num_pins"]
            / def_data["die_area_um2"]
            * 1e4,
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
        features["wirelength_um"]
        is not None
    )

    via_count_available = (
        features["via_count"]
        is not None
    )

    congestion_available = (
        features["congestion"]
        is not None
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

    features["valid_run"] = (
        valid_run
    )

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

    print(
        f"Output: {OUTPUT_FILE}"
    )

    print()

    for key, value in features.items():

        print(
            f"{key:<30}: {value}"
        )

    print()

    if valid_run:

        print("=" * 70)
        print("[SUCCESS] VALID RUN")
        print(
            "All required features are available."
        )
        print("=" * 70)

    else:

        print("=" * 70)
        print("[WARNING] INVALID RUN")
        print(
            "Missing required features:"
        )

        for feature in missing_required:

            print(
                f"  - {feature}"
            )

        print("=" * 70)


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":
    main()
