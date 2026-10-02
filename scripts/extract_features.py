#!/usr/bin/env python3

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path


# ================================================================
# Configuration
# ================================================================

RUN_TAG = os.environ.get("RUN_TAG", "run_test")
ARRAY_SIZE = int(os.environ.get("ARRAY_SIZE", "4"))
DATA_WIDTH = int(os.environ.get("DATA_WIDTH", "8"))
UTIL = float(os.environ.get("UTIL", "50"))
CLK_PERIOD = float(os.environ.get("CLK_PERIOD", "5.0"))

RUN_DIR = Path("systolic_project/runs") / RUN_TAG
NETLIST = Path("systolic_project/synth/systolic_netlist.v")
ODB = RUN_DIR / "final.odb"

OUTPUT = RUN_DIR / "features.json"


# ================================================================
# Utility functions
# ================================================================

def read_text(path):
    if not path.exists():
        return ""

    try:
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def first_float(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                pass

    return None


def first_int(patterns, text):
    value = first_float(patterns, text)

    if value is None:
        return None

    return int(value)


# ================================================================
# Netlist statistics
# ================================================================

def extract_netlist_stats():
    text = read_text(NETLIST)

    if not text:
        return {
            "num_cells": None,
            "num_nets": None,
            "num_pins": None,
            "num_buffers": None,
        }

    # ------------------------------------------------------------
    # Count instantiated standard cells.
    #
    # Example:
    # sky130_fd_sc_hd__and2_1 _123 (...);
    #
    # We deliberately exclude module declarations.
    # ------------------------------------------------------------

    cell_pattern = re.compile(
        r"^\s*(sky130_fd_sc_hd__\S+)\s+(\S+)\s*\(",
        re.MULTILINE
    )

    cells = cell_pattern.findall(text)

    num_cells = len(cells)

    # ------------------------------------------------------------
    # Count nets from wire declarations.
    # ------------------------------------------------------------

    wire_matches = re.findall(
        r"^\s*(?:wire|tri|wand|wor)\b",
        text,
        re.MULTILINE
    )

    num_nets = len(wire_matches)

    # ------------------------------------------------------------
    # Count input/output ports.
    # ------------------------------------------------------------

    input_ports = re.findall(
        r"^\s*input\b",
        text,
        re.MULTILINE
    )

    output_ports = re.findall(
        r"^\s*output\b",
        text,
        re.MULTILINE
    )

    # Also count individual bit-level ports.
    port_names = set()

    port_pattern = re.compile(
        r"\b(?:input|output|inout)\b(?:\s+(?:wire|reg|logic))?"
        r"(?:\s*\[[^\]]+\])?\s+([^;]+);"
    )

    for match in port_pattern.finditer(text):
        declaration = match.group(1)

        for name in declaration.split(","):
            name = name.strip()

            if name:
                port_names.add(name)

    # If the above declaration parser does not work, use a fallback.
    num_pins = len(port_names)

    if num_pins == 0:
        num_pins = len(input_ports) + len(output_ports)

    # ------------------------------------------------------------
    # Count buffers.
    #
    # SKY130 buffer cells generally contain "__buf".
    # We also include clock-buffer style cells.
    # ------------------------------------------------------------

    buffer_count = 0

    for master, instance in cells:
        master_lower = master.lower()

        if (
            "__buf" in master_lower
            or "__clkbuf" in master_lower
            or master_lower.endswith("_buf")
        ):
            buffer_count += 1

    return {
        "num_cells": num_cells if num_cells > 0 else None,
        "num_nets": num_nets if num_nets > 0 else None,
        "num_pins": num_pins if num_pins > 0 else None,
        "num_buffers": buffer_count,
    }


# ================================================================
# Query final OpenROAD database
# ================================================================

def query_odb():
    """
    Query final.odb using OpenROAD itself.

    This avoids depending on the Python OpenROAD module,
    which is not installed in the GitHub Actions environment.
    """

    if not ODB.exists():
        print("[WARNING] final.odb not found.")
        return {}

    tcl_script = r'''
read_db "__ODB__"

set block [ord::get_db_block]

# ------------------------------------------------------------
# Die area
# ------------------------------------------------------------

set die [$block getDieArea]

set die_xmin [$die xMin]
set die_ymin [$die yMin]
set die_xmax [$die xMax]
set die_ymax [$die yMax]

set die_area [expr {
    ($die_xmax - $die_xmin) *
    ($die_ymax - $die_ymin)
}]

puts "METRIC DIE_AREA $die_area"

# ------------------------------------------------------------
# Core area
# ------------------------------------------------------------

set core [$block getCoreArea]

set core_xmin [$core xMin]
set core_ymin [$core yMin]
set core_xmax [$core xMax]
set core_ymax [$core yMax]

set core_area [expr {
    ($core_xmax - $core_xmin) *
    ($core_ymax - $core_ymin)
}]

puts "METRIC CORE_AREA $core_area"

# ------------------------------------------------------------
# Instance count
# ------------------------------------------------------------

set insts [$block getInsts]

puts "METRIC NUM_CELLS [llength $insts]"

# ------------------------------------------------------------
# Net count
# ------------------------------------------------------------

set nets [$block getNets]

puts "METRIC NUM_NETS [llength $nets]"

# ------------------------------------------------------------
# Instance pin count
# ------------------------------------------------------------

set inst_pin_count 0

foreach inst $insts {
    set inst_iterms [$inst getITerms]
    set inst_pin_count [expr {
        $inst_pin_count + [llength $inst_iterms]
    }]
}

puts "METRIC NUM_PINS $inst_pin_count"

# ------------------------------------------------------------
# Buffer count
# ------------------------------------------------------------

set buffer_count 0

foreach inst $insts {

    set master [$inst getMaster]

    if {$master == ""} {
        continue
    }

    set master_name [$master getName]
    set name_lower [string tolower $master_name]

    if {
        [string match "*__buf*" $name_lower] ||
        [string match "*__clkbuf*" $name_lower]
    } {
        incr buffer_count
    }
}

puts "METRIC NUM_BUFFERS $buffer_count"

# ------------------------------------------------------------
# Routing/via count
#
# Count all dbVia objects currently present in the design.
# ------------------------------------------------------------

set via_count 0

foreach net $nets {

    set vias [$net getVias]

    set via_count [expr {
        $via_count + [llength $vias]
    }]
}

puts "METRIC VIA_COUNT $via_count"

exit
'''

    tcl_script = tcl_script.replace(
        "__ODB__",
        str(ODB.resolve()).replace("\\", "/")
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".tcl",
        delete=False
    ) as f:
        f.write(tcl_script)
        script_path = f.name

    try:
        result = subprocess.run(
            [
                "openroad",
                "-exit",
                script_path,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
        )

        output = result.stdout

    except Exception as exc:
        print(f"[WARNING] OpenROAD ODB query failed: {exc}")
        return {}

    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass

    metrics = {}

    for line in output.splitlines():

        match = re.match(
            r"METRIC\s+(\S+)\s+([-+0-9.eE]+)",
            line.strip()
        )

        if not match:
            continue

        key = match.group(1)
        value = match.group(2)

        try:
            value = float(value)

            if value.is_integer():
                value = int(value)

            metrics[key] = value

        except ValueError:
            pass

    if not metrics:
        print("[WARNING] No ODB metrics were extracted.")

    return metrics


# ================================================================
# Wirelength
# ================================================================

def extract_wirelength():
    candidates = [
        RUN_DIR / "wirelength_final.rpt",
        RUN_DIR / "wirelength_detailed.rpt",
        RUN_DIR / "wirelength_global.rpt",
    ]

    for path in candidates:

        text = read_text(path)

        if not text.strip():
            continue

        # --------------------------------------------------------
        # Typical possible formats
        # --------------------------------------------------------

        patterns = [
            r"total_wl\s+([0-9]+(?:\.[0-9]+)?)",
            r"total\s+wirelength\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"wirelength\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
            r"\bwl\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        ]

        value = first_float(patterns, text)

        if value is not None:
            return value

    return None


# ================================================================
# Congestion
# ================================================================

def extract_congestion():
    path = RUN_DIR / "congestion.rpt"

    text = read_text(path)

    if not text.strip():
        return None

    # ------------------------------------------------------------
    # Try several common OpenROAD congestion formats.
    # ------------------------------------------------------------

    patterns = [
        r"overflow\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)",
        r"total\s+overflow\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)",
        r"overflow\s+([0-9]+(?:\.[0-9]+)?)",
        r"total.*?overflow.*?([0-9]+(?:\.[0-9]+)?)",
    ]

    value = first_float(patterns, text)

    return value


# ================================================================
# Timing
# ================================================================

def extract_timing():
    setup_wns = first_float(
        [
            r"\bwns\s+(-?[0-9]+(?:\.[0-9]+)?)",
            r"wns\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(RUN_DIR / "wns_setup.rpt")
    )

    setup_tns = first_float(
        [
            r"\btns\s+(-?[0-9]+(?:\.[0-9]+)?)",
            r"tns\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(RUN_DIR / "tns_setup.rpt")
    )

    hold_wns = first_float(
        [
            r"\bwns\s+(-?[0-9]+(?:\.[0-9]+)?)",
            r"wns\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(RUN_DIR / "wns_hold.rpt")
    )

    hold_tns = first_float(
        [
            r"\btns\s+(-?[0-9]+(?:\.[0-9]+)?)",
            r"tns\s*[:=]\s*(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(RUN_DIR / "tns_hold.rpt")
    )

    # ------------------------------------------------------------
    # Convert ns -> ps.
    #
    # OpenROAD timing reports are in ns.
    # ------------------------------------------------------------

    if setup_wns is not None:
        setup_wns *= 1000.0

    if setup_tns is not None:
        setup_tns *= 1000.0

    if hold_wns is not None:
        hold_wns *= 1000.0

    if hold_tns is not None:
        hold_tns *= 1000.0

    return {
        "wns_setup_ps": setup_wns,
        "tns_setup_ps": setup_tns,
        "wns_hold_ps": hold_wns,
        "tns_hold_ps": hold_tns,
    }


# ================================================================
# Main extraction
# ================================================================

def main():

    print("=" * 70)
    print("FEATURE EXTRACTION")
    print("=" * 70)

    print(f"Run tag : {RUN_TAG}")
    print(f"Run dir : {RUN_DIR}")

    RUN_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------
    # Basic metadata
    # ------------------------------------------------------------

    features = {
        "run_tag": RUN_TAG,
        "array_size": ARRAY_SIZE,
        "data_width": DATA_WIDTH,
        "utilization": UTIL,
        "clk_period_ns": CLK_PERIOD,

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
        "wns_hold_ps": None,

        "wirelength_available": False,
        "congestion_available": False,
        "timing_available": False,
        "valid_run": False,
    }

    # ------------------------------------------------------------
    # Netlist
    # ------------------------------------------------------------

    netlist_stats = extract_netlist_stats()

    features.update(netlist_stats)

    # ------------------------------------------------------------
    # ODB
    # ------------------------------------------------------------

    odb_metrics = query_odb()

    if "DIE_AREA" in odb_metrics:
        features["die_area_u2"] = odb_metrics["DIE_AREA"]

    if "CORE_AREA" in odb_metrics:
        features["core_area_u2"] = odb_metrics["CORE_AREA"]

    # Prefer ODB counts when available.
    if "NUM_CELLS" in odb_metrics:
        features["num_cells"] = odb_metrics["NUM_CELLS"]

    if "NUM_NETS" in odb_metrics:
        features["num_nets"] = odb_metrics["NUM_NETS"]

    if "NUM_PINS" in odb_metrics:
        features["num_pins"] = odb_metrics["NUM_PINS"]

    if "NUM_BUFFERS" in odb_metrics:
        features["num_buffers"] = odb_metrics["NUM_BUFFERS"]

    if "VIA_COUNT" in odb_metrics:
        features["via_count"] = odb_metrics["VIA_COUNT"]

    # ------------------------------------------------------------
    # Wirelength
    # ------------------------------------------------------------

    wirelength = extract_wirelength()

    if wirelength is not None:
        features["wirelength_u"] = wirelength
        features["wirelength_available"] = True
    else:
        print("[WARNING] Wirelength could not be extracted.")

    # ------------------------------------------------------------
    # Congestion
    # ------------------------------------------------------------

    congestion = extract_congestion()

    if congestion is not None:
        features["congestion_overflow_pct"] = congestion
        features["congestion_available"] = True
    else:
        print("[WARNING] Congestion could not be extracted.")

    # ------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------

    timing = extract_timing()

    features.update(timing)

    if (
        timing["wns_setup_ps"] is not None
        and timing["tns_setup_ps"] is not None
    ):
        features["timing_available"] = True
    else:
        print("[WARNING] Setup timing could not be completely extracted.")

    # ------------------------------------------------------------
    # ODB existence
    # ------------------------------------------------------------

    if ODB.exists():
        print("[INFO] final.odb exists.")
    else:
        print("[WARNING] final.odb does not exist.")

    # ------------------------------------------------------------
    # Validity
    # ------------------------------------------------------------

    features["valid_run"] = bool(
        ODB.exists()
        and features["num_cells"] is not None
        and features["num_nets"] is not None
        and features["num_pins"] is not None
        and features["die_area_u2"] is not None
        and features["core_area_u2"] is not None
    )

    # ------------------------------------------------------------
    # Save JSON
    # ------------------------------------------------------------

    with OUTPUT.open("w") as f:
        json.dump(features, f, indent=2)

    # ------------------------------------------------------------
    # Display
    # ------------------------------------------------------------

    print("=" * 70)
    print("FEATURE EXTRACTION COMPLETE")
    print("=" * 70)

    print(f"Output: {OUTPUT}")
    print()

    for key, value in features.items():
        print(f"{key:30s}: {value}")


if __name__ == "__main__":
    main()
