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

WNS_SETUP = RUN_DIR / "wns_setup.rpt"
TNS_SETUP = RUN_DIR / "tns_setup.rpt"

CONGESTION = RUN_DIR / "congestion.rpt"
GLOBAL_ROUTE_REPORT = RUN_DIR / "global_route.rpt"
OPENROAD_LOG = RUN_DIR / "openroad_log.txt"

WIRELENGTH_FINAL = RUN_DIR / "wirelength_final.rpt"
WIRELENGTH_DETAILED = RUN_DIR / "wirelength_detailed.rpt"


# ================================================================
# BASIC HELPERS
# ================================================================

def safe_float(value):
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except Exception:
        pass
    return None


def read_text(path):
    if not path.exists():
        return ""

    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def extract_first_number(text):
    if not text:
        return None

    matches = re.findall(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?",
        text
    )

    for value in matches:
        number = safe_float(value)

        if number is not None:
            return number

    return None


# ================================================================
# ENVIRONMENT FEATURES
# ================================================================

def get_environment_features():

    return {
        "run_tag": RUN_TAG,
        "array_size": int(
            os.environ.get("ARRAY_SIZE", "4")
        ),
        "data_width": int(
            os.environ.get("DATA_WIDTH", "8")
        ),
        "utilization": float(
            os.environ.get("UTIL", "50")
        ),
        "clock_period": float(
            os.environ.get("CLK_PERIOD", "5.0")
        ),
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

        # Top-level IO pins only.
        "num_pins": 0,

        # Actual instance-net connections.
        "num_instance_pins": 0,

        "num_registers": 0,
        "num_buffers": 0,

        "components": {},
        "nets": {},

        # DEF-declared via names.
        "via_names": set(),
    }

    if not text:
        return result

    # ============================================================
    # DIE AREA
    # ============================================================

    m = re.search(
        r"DIEAREA\s*"
        r"\(\s*(-?\d+)\s+(-?\d+)\s*\)"
        r"\s*"
        r"\(\s*(-?\d+)\s+(-?\d+)\s*\)",
        text,
        re.S
    )

    if m:

        x0, y0, x1, y1 = map(
            int,
            m.groups()
        )

        dbu = 1000.0

        width = abs(x1 - x0) / dbu
        height = abs(y1 - y0) / dbu

        result["die_area_um2"] = (
            width * height
        )

    # ============================================================
    # COMPONENTS
    # ============================================================

    comp_section = re.search(
        r"COMPONENTS\s+\d+\s*;(.*?)END COMPONENTS",
        text,
        re.S | re.I
    )

    if comp_section:

        component_text = comp_section.group(1)

        # Parse one component at a time.
        component_blocks = re.findall(
            r"(?ms)^\s*-\s+(\S+)\s+(\S+).*?"
            r"(?=^\s*-\s+\S+|\Z)",
            component_text
        )

        for inst, master_and_body in component_blocks:

            # The above expression gives only two groups because
            # the body is included in the second group only in
            # some DEF layouts. Use a direct search below instead.
            pass

        # More reliable block parser.
        block_pattern = re.compile(
            r"(?ms)^\s*-\s+(\S+)\s+(\S+)"
            r"(.*?)(?=^\s*-\s+\S+|\Z)"
        )

        for match in block_pattern.finditer(
            component_text
        ):

            inst = match.group(1)
            master = match.group(2)
            body = match.group(3)

            placed = re.search(
                r"\+\s+(?:PLACED|FIXED)\s+"
                r"\(\s*(-?\d+)\s+(-?\d+)\s*\)",
                body,
                re.I
            )

            if not placed:
                continue

            x = int(placed.group(1))
            y = int(placed.group(2))

            result["components"][inst] = {
                "master": master,
                "x": x,
                "y": y,
            }

    result["num_cells"] = len(
        result["components"]
    )

    # ============================================================
    # REGISTER / BUFFER CLASSIFICATION
    # ============================================================

    for data in result["components"].values():

        master = data["master"].lower()

        if re.search(
            r"(dff|dfr|dfb|dfx|dlr|dlh|latch)",
            master
        ):
            result["num_registers"] += 1

        if re.search(
            r"(^|_)buf|buf",
            master
        ):
            result["num_buffers"] += 1

    # ============================================================
    # VIA DECLARATIONS
    # ============================================================

    via_section = re.search(
        r"VIAS\s+\d+\s*;(.*?)END VIAS",
        text,
        re.S | re.I
    )

    if via_section:

        via_text = via_section.group(1)

        via_matches = re.findall(
            r"^\s*-\s+(\S+)",
            via_text,
            re.M
        )

        result["via_names"] = set(
            v.lower()
            for v in via_matches
        )

    # ============================================================
    # NETS
    # ============================================================

    nets_section = re.search(
        r"NETS\s+\d+\s*;(.*?)END NETS",
        text,
        re.S | re.I
    )

    if nets_section:

        net_text = nets_section.group(1)

        # DEF net blocks begin with "- netname".
        net_pattern = re.compile(
            r"(?ms)^\s*-\s+(\S+)"
            r"(.*?)(?=^\s*-\s+\S+|\Z)"
        )

        for match in net_pattern.finditer(
            net_text
        ):

            net_name = match.group(1)
            body = match.group(2)

            result["nets"][net_name] = body

    result["num_nets"] = len(
        result["nets"]
    )

    # ============================================================
    # TOP-LEVEL PINS
    # ============================================================

    pin_section = re.search(
        r"PINS\s+\d+\s*;(.*?)END PINS",
        text,
        re.S | re.I
    )

    if pin_section:

        pin_matches = re.findall(
            r"^\s*-\s+\S+",
            pin_section.group(1),
            re.M
        )

        result["num_pins"] = len(
            pin_matches
        )

    # ============================================================
    # ACTUAL INSTANCE PIN CONNECTIONS
    # ============================================================

    total_instance_connections = 0

    connection_pattern = re.compile(
        r"\(\s*(\S+)\s+(\S+)\s*\)"
    )

    for body in result["nets"].values():

        for inst, pin in connection_pattern.findall(
            body
        ):

            if inst in result["components"]:
                total_instance_connections += 1

    result["num_instance_pins"] = (
        total_instance_connections
    )

    return result


# ================================================================
# NET CLASSIFICATION
# ================================================================

def is_power_ground_net(net_name):

    name = net_name.upper()

    power_patterns = [
        "VDD",
        "VSS",
        "VPWR",
        "VGND",
        "VCCD",
        "VSSD",
        "VCCA",
        "VSSA",
        "AVDD",
        "AVSS",
        "DVDD",
        "DVSS",
    ]

    for pattern in power_patterns:

        if (
            name == pattern
            or name.startswith(pattern)
        ):
            return True

    return False


def is_clock_net(net_name, body=""):

    name = net_name.lower()

    clock_keywords = [
        "clk",
        "clock",
        "scan_clk",
        "gclk",
    ]

    for keyword in clock_keywords:

        if keyword in name:
            return True

    # Some generated designs identify the clock
    # only in the connection/body text.
    if re.search(
        r"\b(clock|clk)\b",
        body,
        re.I
    ):
        return True

    return False


def get_signal_connections(body, components):

    connection_pattern = re.compile(
        r"\(\s*(\S+)\s+(\S+)\s*\)"
    )

    connections = []

    for inst, pin in connection_pattern.findall(
        body
    ):

        if inst in components:

            connections.append(
                {
                    "inst": inst,
                    "pin": pin,
                }
            )

    return connections


# ================================================================
# COMPONENT / PLACEMENT FEATURES
# ================================================================

def calculate_component_features(
    def_data,
    requested_utilization
):

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

    xs = [
        c["x"]
        for c in components.values()
    ]

    ys = [
        c["y"]
        for c in components.values()
    ]

    x_spread = (
        max(xs) - min(xs)
    ) / 1000.0

    y_spread = (
        max(ys) - min(ys)
    ) / 1000.0

    # ============================================================
    # LOCAL PLACEMENT DENSITY
    #
    # IMPORTANT:
    #
    # The previous implementation normalized the grid such that
    # mean_density was ALWAYS 100%.
    #
    # That destroys information.
    #
    # Here the average bin density is anchored to the requested
    # global placement utilization.
    #
    # Therefore:
    #
    #     mean_density ~= utilization
    #
    # while local clustering can make max_density > utilization.
    # ============================================================

    nx = 10
    ny = 10

    xmin = min(xs)
    xmax = max(xs)

    ymin = min(ys)
    ymax = max(ys)

    xrange = max(
        xmax - xmin,
        1
    )

    yrange = max(
        ymax - ymin,
        1
    )

    grid = [
        [
            0
            for _ in range(nx)
        ]
        for _ in range(ny)
    ]

    for c in components.values():

        gx = int(
            (
                c["x"] - xmin
            )
            / xrange
            * nx
        )

        gy = int(
            (
                c["y"] - ymin
            )
            / yrange
            * ny
        )

        gx = min(
            max(gx, 0),
            nx - 1
        )

        gy = min(
            max(gy, 0),
            ny - 1
        )

        grid[gy][gx] += 1

    counts = [
        count
        for row in grid
        for count in row
    ]

    mean_count = (
        sum(counts)
        / len(counts)
    )

    if mean_count <= 0:
        densities = [
            0.0
            for _ in counts
        ]
    else:

        densities = [

            (
                count
                / mean_count
            )
            * requested_utilization

            for count in counts
        ]

    mean_density = (
        sum(densities)
        / len(densities)
    )

    variance = (
        sum(
            (
                d - mean_density
            ) ** 2
            for d in densities
        )
        / len(densities)
    )

    std_density = math.sqrt(
        variance
    )

    max_density = max(
        densities
    )

    return {
        "x_spread": round(
            x_spread,
            6
        ),

        "y_spread": round(
            y_spread,
            6
        ),

        "max_density": round(
            max_density,
            6
        ),

        "mean_density": round(
            mean_density,
            6
        ),

        "std_density": round(
            std_density,
            6
        ),

        "pin_density": None,
    }


# ================================================================
# FANOUT
# ================================================================

def calculate_fanout_features(def_data):

    components = def_data["components"]
    nets = def_data["nets"]

    fanouts = []

    for net_name, body in nets.items():

        if is_power_ground_net(
            net_name
        ):
            continue

        # Do not let global clock distribution dominate
        # the ordinary signal-fanout statistics.
        if is_clock_net(
            net_name,
            body
        ):
            continue

        connections = get_signal_connections(
            body,
            components
        )

        if len(connections) < 2:
            continue

        # One connection is normally the driver.
        # Remaining connections are sinks.
        sink_count = len(
            connections
        ) - 1

        if sink_count < 1:
            continue

        fanouts.append(
            sink_count
        )

    if not fanouts:

        return {
            "avg_fanout": None,
            "max_fanout": None,
        }

    return {
        "avg_fanout": round(
            sum(fanouts)
            / len(fanouts),
            6
        ),

        "max_fanout": int(
            max(fanouts)
        ),
    }


# ================================================================
# INSTANCE PIN DENSITY
# ================================================================

def calculate_pin_density(
    def_data
):

    die_area = def_data[
        "die_area_um2"
    ]

    instance_pins = def_data[
        "num_instance_pins"
    ]

    if (
        die_area is None
        or die_area <= 0
        or instance_pins <= 0
    ):
        return None

    # pins / 10,000 um^2
    return round(
        instance_pins
        / die_area
        * 1e4,
        6
    )


# ================================================================
# ROUTING REPORT WIRELENGTH
# ================================================================

def extract_wirelength_from_report(
    path
):

    text = read_text(path)

    if not text.strip():
        return None

    # ============================================================
    # Common OpenROAD report formats.
    # ============================================================

    patterns = [

        # wirelength = 12345
        r"\bwirelength\b\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",

        # total wire length = 12345
        r"\btotal\s+wire\s+length\b"
        r"\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",

        # Wire length: 12345
        r"\bwire\s+length\b"
        r"\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",

        # HPWL / wire length style reports
        r"\bHPWL\b\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            value = safe_float(
                match.group(1)
            )

            if (
                value is not None
                and value > 0
            ):

                return round(
                    value,
                    6
                )

    # Search lines containing "wire".
    for line in text.splitlines():

        if "wire" not in line.lower():
            continue

        numbers = re.findall(
            r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)",
            line
        )

        if numbers:

            # Use the last number on a wirelength summary line.
            for value_text in reversed(
                numbers
            ):

                value = safe_float(
                    value_text
                )

                if (
                    value is not None
                    and value > 0
                ):
                    return round(
                        value,
                        6
                    )

    return None


# ================================================================
# ROUTED NET / DEF ROUTING PARSER
# ================================================================

def calculate_routing_from_def(
    def_data,
    def_file
):

    text = read_text(
        def_file
    )

    if not text:

        return {
            "wirelength_um": None,
            "via_count": None,
            "routed_net_count": None,
        }

    nets_section = re.search(
        r"NETS\s+\d+\s*;(.*?)END NETS",
        text,
        re.S | re.I
    )

    if not nets_section:

        return {
            "wirelength_um": None,
            "via_count": None,
            "routed_net_count": None,
        }

    net_text = nets_section.group(1)

    net_blocks = re.findall(
        r"(?ms)^\s*-\s+\S+.*?"
        r"(?=^\s*-\s+\S+|\Z)",
        net_text
    )

    routed_net_count = 0

    wirelength_dbu = 0.0

    via_count = 0

    declared_vias = def_data[
        "via_names"
    ]

    # Coordinate pattern.
    coordinate_pattern = re.compile(
        r"\(\s*(-?\d+)\s+(-?\d+)\s*\)"
    )

    for block in net_blocks:

        if not re.search(
            r"\bROUTED\b|\bFIXED\b",
            block,
            re.I
        ):
            continue

        routed_net_count += 1

        # ========================================================
        # Isolate routing after ROUTED/FIXED.
        # This prevents pin coordinates before the routing
        # statement from being included.
        # ========================================================

        route_matches = list(
            re.finditer(
                r"\b(?:ROUTED|FIXED)\b",
                block,
                re.I
            )
        )

        if not route_matches:
            continue

        route_text = block[
            route_matches[0].start():
        ]

        # ========================================================
        # Count vias by matching DEF-declared via names.
        #
        # This handles names such as:
        #
        #   VIA12
        #   M2_M3
        #   VIA_M2_M3
        #
        # rather than only "via123".
        # ========================================================

        if declared_vias:

            tokens = re.findall(
                r"[A-Za-z_][A-Za-z0-9_.$/-]*",
                route_text
            )

            for token in tokens:

                if token.lower() in declared_vias:

                    via_count += 1

        # ========================================================
        # Safer route wirelength.
        #
        # Split at NEW because each NEW route starts a new path.
        # ========================================================

        route_parts = re.split(
            r"\bNEW\b",
            route_text,
            flags=re.I
        )

        for part in route_parts:

            coords = [
                (
                    int(x),
                    int(y)
                )
                for x, y in
                coordinate_pattern.findall(
                    part
                )
            ]

            if len(coords) < 2:
                continue

            for i in range(
                1,
                len(coords)
            ):

                x1, y1 = coords[
                    i - 1
                ]

                x2, y2 = coords[
                    i
                ]

                wirelength_dbu += (
                    abs(x2 - x1)
                    + abs(y2 - y1)
                )

    wirelength_um = None

    if wirelength_dbu > 0:

        wirelength_um = round(
            wirelength_dbu / 1000.0,
            6
        )

    return {
        "wirelength_um":
            wirelength_um,

        "via_count":
            int(via_count),

        "routed_net_count":
            (
                int(routed_net_count)
                if routed_net_count > 0
                else None
            ),
    }


# ================================================================
# AUTHORITATIVE ROUTING FEATURES
# ================================================================

def calculate_routing_features(
    def_data,
    def_file
):

    # ------------------------------------------------------------
    # Prefer OpenROAD wirelength report.
    # ------------------------------------------------------------

    wirelength = (
        extract_wirelength_from_report(
            WIRELENGTH_FINAL
        )
    )

    if wirelength is None:

        wirelength = (
            extract_wirelength_from_report(
                WIRELENGTH_DETAILED
            )
        )

    # ------------------------------------------------------------
    # DEF fallback.
    # ------------------------------------------------------------

    def_routing = (
        calculate_routing_from_def(
            def_data,
            def_file
        )
    )

    if wirelength is None:

        wirelength = def_routing[
            "wirelength_um"
        ]

    return {
        "wirelength_um":
            wirelength,

        "via_count":
            def_routing[
                "via_count"
            ],

        "routed_net_count":
            def_routing[
                "routed_net_count"
            ],
    }


# ================================================================
# ESTIMATED WIRELENGTH / HPWL
# ================================================================

def calculate_estimated_wirelength(
    def_data
):

    components = def_data[
        "components"
    ]

    if not components:
        return None

    total_dbu = 0.0

    for net_name, body in (
        def_data["nets"].items()
    ):

        if is_power_ground_net(
            net_name
        ):
            continue

        refs = re.findall(
            r"\(\s+(\S+)\s+\S+\s*\)",
            body
        )

        points = []

        seen = set()

        for ref in refs:

            if (
                ref in components
                and ref not in seen
            ):

                c = components[
                    ref
                ]

                points.append(
                    (
                        c["x"],
                        c["y"]
                    )
                )

                seen.add(ref)

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

        total_dbu += (
            max(xs) - min(xs)
        )

        total_dbu += (
            max(ys) - min(ys)
        )

    if total_dbu <= 0:
        return None

    return round(
        total_dbu / 1000.0,
        6
    )


# ================================================================
# CONGESTION
# ================================================================

def extract_congestion():

    def parse_congestion_value(
        text
    ):

        if not text:
            return None

        # --------------------------------------------------------
        # Look ONLY for routing-related lines.
        # Do NOT scan every percentage in openroad_log.txt.
        # --------------------------------------------------------

        routing_keywords = (
            "congestion",
            "overflow",
            "routing",
            "gcell",
        )

        for line in text.splitlines():

            lower = line.lower()

            if not any(
                keyword in lower
                for keyword in routing_keywords
            ):
                continue

            matches = re.findall(
                r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
                r"\s*%",
                line
            )

            for value_text in matches:

                value = safe_float(
                    value_text.replace(
                        "%",
                        ""
                    ).strip()
                )

                if (
                    value is not None
                    and 0.0 <= value <= 1000.0
                ):

                    return round(
                        value,
                        6
                    )

        # --------------------------------------------------------
        # Total row.
        # --------------------------------------------------------

        match = re.search(
            r"^\s*Total\b.*?"
            r"([-+]?(?:\d+(?:\.\d*)?|\.\d+))"
            r"\s*%",
            text,
            re.I | re.M
        )

        if match:

            value = safe_float(
                match.group(1)
            )

            if (
                value is not None
                and 0 <= value <= 1000
            ):
                return round(
                    value,
                    6
                )

        return None

    def confirms_zero_overflow(
        text
    ):

        if not text:
            return False

        patterns = [

            r"no\s+overflowing\s+gcell",

            r"no\s+overflowing\s+gcells",

            r"no\s+routing\s+overflow",

            r"zero\s+routing\s+overflow",

            r"routing\s+overflow\s*[:=]\s*0",

            r"total\s+overflow\s*[:=]\s*0",

            r"\boverflow\s*[:=]\s*0",

        ]

        return any(
            re.search(
                pattern,
                text,
                re.I
            )
            for pattern in patterns
        )

    # ============================================================
    # 1. global_route.rpt
    # ============================================================

    text = read_text(
        GLOBAL_ROUTE_REPORT
    )

    value = parse_congestion_value(
        text
    )

    if value is not None:

        print(
            "[INFO] Congestion extracted "
            f"from global_route.rpt: {value}"
        )

        return value

    if confirms_zero_overflow(
        text
    ):

        print(
            "[INFO] Global routing report "
            "confirms zero overflow."
        )

        return 0.0

    # ============================================================
    # 2. congestion.rpt
    # ============================================================

    text = read_text(
        CONGESTION
    )

    value = parse_congestion_value(
        text
    )

    if value is not None:

        print(
            "[INFO] Congestion extracted "
            f"from congestion.rpt: {value}"
        )

        return value

    if confirms_zero_overflow(
        text
    ):

        print(
            "[INFO] congestion.rpt confirms "
            "zero overflow."
        )

        return 0.0

    # ============================================================
    # 3. OpenROAD log
    # ============================================================

    text = read_text(
        OPENROAD_LOG
    )

    # Only use routing-specific lines.
    value = parse_congestion_value(
        text
    )

    if value is not None:

        print(
            "[INFO] Congestion extracted "
            f"from routing lines in openroad_log.txt: "
            f"{value}"
        )

        return value

    if confirms_zero_overflow(
        text
    ):

        print(
            "[INFO] OpenROAD log confirms "
            "zero routing overflow."
        )

        return 0.0

    print(
        "[WARNING] No reliable congestion "
        "information found."
    )

    return None


# ================================================================
# TIMING SCALAR REPORT
# ================================================================

def extract_scalar_report(
    path,
    metric_name
):

    text = read_text(
        path
    )

    if not text.strip():
        return None

    pattern = (
        rf"\b{re.escape(metric_name)}\b"
        rf"\s*[:=]?\s*"
        rf"(-?(?:\d+(?:\.\d*)?|\.\d+)"
        rf"(?:[eE][+-]?\d+)?)"
    )

    match = re.search(
        pattern,
        text,
        re.I
    )

    if not match:
        return None

    return safe_float(
        match.group(1)
    )


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
        return result

    # ============================================================
    # Slack values
    # ============================================================

    slack_values = []

    patterns = [

        r"([-+]?\d+(?:\.\d+)?)"
        r"\s+slack\s+"
        r"\((?:VIOLATED|MET)\)",

        r"\bslack\b\s*[:=]\s*"
        r"([-+]?\d+(?:\.\d+)?)",
    ]

    for pattern in patterns:

        values = re.findall(
            pattern,
            text,
            re.I
        )

        if values:

            for value in values:

                parsed = safe_float(
                    value
                )

                if parsed is not None:
                    slack_values.append(
                        parsed
                    )

            if slack_values:
                break

    if slack_values:

        result["WNS"] = round(
            min(slack_values),
            6
        )

        negative = [
            value
            for value in slack_values
            if value < 0
        ]

        result["TNS"] = round(
            sum(negative)
            if negative
            else 0.0,
            6
        )

    # ============================================================
    # Find worst timing path.
    # ============================================================

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

        matches = re.findall(
            r"([-+]?\d+(?:\.\d+)?)"
            r"\s+slack\s+"
            r"\((?:VIOLATED|MET)\)",
            block,
            re.I
        )

        if not matches:
            continue

        slack = safe_float(
            matches[-1]
        )

        if slack is None:
            continue

        if (
            worst_slack is None
            or slack < worst_slack
        ):

            worst_slack = slack
            worst_block = block

    if worst_block is None:
        return result

    # ============================================================
    # Extract path cell instances.
    # ============================================================

    cell_pattern = re.compile(
        r"([A-Za-z0-9_$.\[\]/-]+)"
        r"/[A-Za-z0-9_$.\[\]-]+"
        r"\s+\("
        r"(?:sky130_fd_sc_hd__)?"
        r"([A-Za-z0-9_]+)"
        r"\)",
        re.I
    )

    cells = []

    for inst, master in cell_pattern.findall(
        worst_block
    ):

        cells.append(
            {
                "inst": inst,
                "master": master.lower(),
            }
        )

    # ============================================================
    # Logic depth
    # ============================================================

    combinational_cells = []

    for cell in cells:

        if not re.search(
            r"(dff|dfr|dfb|dfx|dlr|dlh|latch)",
            cell["master"],
            re.I
        ):

            combinational_cells.append(
                cell
            )

    if combinational_cells:

        result["logic_depth"] = len(
            combinational_cells
        )

    # ============================================================
    # Critical path physical distance
    # ============================================================

    components = parse_def(
        FINAL_DEF
    )["components"]

    path_points = []

    for cell in cells:

        inst = cell["inst"]

        if inst not in components:
            continue

        c = components[
            inst
        ]

        path_points.append(
            (
                c["x"],
                c["y"]
            )
        )

    if len(path_points) >= 2:

        distance_dbu = 0.0

        for i in range(
            1,
            len(path_points)
        ):

            x1, y1 = path_points[
                i - 1
            ]

            x2, y2 = path_points[
                i
            ]

            distance_dbu += (
                abs(x2 - x1)
                + abs(y2 - y1)
            )

        result[
            "crit_path_wirelength"
        ] = round(
            distance_dbu / 1000.0,
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

    if not text.strip():

        return {
            "hold_WNS": None,
            "hold_TNS": None,
        }

    slack_values = []

    values = re.findall(
        r"([-+]?\d+(?:\.\d+)?)"
        r"\s+slack\s+"
        r"\((?:VIOLATED|MET)\)",
        text,
        re.I
    )

    for value in values:

        parsed = safe_float(
            value
        )

        if parsed is not None:
            slack_values.append(
                parsed
            )

    if not slack_values:

        return {
            "hold_WNS": None,
            "hold_TNS": None,
        }

    return {
        "hold_WNS": round(
            min(slack_values),
            6
        ),

        "hold_TNS": round(
            sum(
                v
                for v in slack_values
                if v < 0
            ),
            6
        ),
    }


# ================================================================
# MAIN
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

    # ============================================================
    # Required files
    # ============================================================

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

    # ============================================================
    # Environment
    # ============================================================

    env = get_environment_features()

    # ============================================================
    # DEF
    # ============================================================

    def_data = parse_def(
        FINAL_DEF
    )

    # ============================================================
    # Placement
    # ============================================================

    placement = (
        calculate_component_features(
            def_data,
            env["utilization"]
        )
    )

    # ============================================================
    # Fanout
    # ============================================================

    fanout = (
        calculate_fanout_features(
            def_data
        )
    )

    # ============================================================
    # Pin density
    # ============================================================

    pin_density = (
        calculate_pin_density(
            def_data
        )
    )

    # ============================================================
    # Routing
    # ============================================================

    routing = (
        calculate_routing_features(
            def_data,
            FINAL_DEF
        )
    )

    # ============================================================
    # Estimated wirelength
    # ============================================================

    estimated_wirelength = (
        calculate_estimated_wirelength(
            def_data
        )
    )

    # ============================================================
    # Congestion
    # ============================================================

    congestion = (
        extract_congestion()
    )

    # ============================================================
    # Timing
    # ============================================================

    timing = parse_timing_report()

    # Authoritative WNS.
    setup_wns = extract_scalar_report(
        WNS_SETUP,
        "wns"
    )

    if setup_wns is not None:

        timing["WNS"] = round(
            setup_wns,
            6
        )

    # Authoritative TNS.
    setup_tns = extract_scalar_report(
        TNS_SETUP,
        "tns"
    )

    if setup_tns is not None:

        timing["TNS"] = round(
            setup_tns,
            6
        )

    # ============================================================
    # Hold
    # ============================================================

    hold = parse_hold_timing()

    # ============================================================
    # Construct features
    # ============================================================

    features = {

        "run_tag":
            RUN_TAG,

        "array_size":
            env["array_size"],

        "data_width":
            env["data_width"],

        # ---------------- CORE 17 ----------------

        "max_density":
            placement["max_density"],

        "mean_density":
            placement["mean_density"],

        "std_density":
            placement["std_density"],

        "pin_density":
            pin_density,

        "avg_fanout":
            fanout["avg_fanout"],

        "max_fanout":
            fanout["max_fanout"],

        "x_spread":
            placement["x_spread"],

        "y_spread":
            placement["y_spread"],

        "num_registers":
            def_data["num_registers"],

        "logic_depth":
            timing["logic_depth"],

        "crit_path_wirelength":
            timing["crit_path_wirelength"],

        "estimated_wirelength":
            estimated_wirelength,

        "congestion":
            congestion,

        "WNS":
            timing["WNS"],

        "TNS":
            timing["TNS"],

        "utilization":
            env["utilization"],

        "clock_period":
            env["clock_period"],

        # ---------------- ADDITIONAL PD ----------------

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

        # Top-level IO pins.
        "num_pins":
            def_data["num_pins"],

        "num_buffers":
            def_data["num_buffers"],
    }

    # ============================================================
    # Availability
    # ============================================================

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

    # ============================================================
    # Required fields
    # ============================================================

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

    # ============================================================
    # Metadata
    # ============================================================

    features[
        "wirelength_available"
    ] = wirelength_available

    features[
        "via_count_available"
    ] = via_count_available

    features[
        "congestion_available"
    ] = congestion_available

    features[
        "timing_available"
    ] = timing_available

    features[
        "valid_run"
    ] = valid_run

    features[
        "missing_required_features"
    ] = missing_required

    # ============================================================
    # Write
    # ============================================================

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

    # ============================================================
    # Report
    # ============================================================

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
