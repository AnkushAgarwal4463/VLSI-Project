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

NETLIST = Path(
    "systolic_project/synth/systolic_netlist.v"
)

ODB = RUN_DIR / "final.odb"

DEF = RUN_DIR / "final.def"

OUTPUT = RUN_DIR / "features.json"


# ================================================================
# Basic utilities
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

        match = re.search(
            pattern,
            text,
            re.IGNORECASE | re.MULTILINE
        )

        if match:

            try:
                return float(match.group(1))

            except (ValueError, IndexError):
                pass

    return None


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
    # Standard-cell instances
    # ------------------------------------------------------------

    cell_pattern = re.compile(
        r"^\s*(sky130_fd_sc_hd__\S+)\s+(\S+)\s*\(",
        re.MULTILINE
    )

    cells = cell_pattern.findall(text)

    num_cells = len(cells)

    # ------------------------------------------------------------
    # Nets
    # ------------------------------------------------------------

    wire_matches = re.findall(
        r"^\s*(?:wire|tri|wand|wor)\b",
        text,
        re.MULTILINE
    )

    num_nets = len(wire_matches)

    # ------------------------------------------------------------
    # Ports / pins
    # ------------------------------------------------------------

    port_names = set()

    port_pattern = re.compile(
        r"\b(?:input|output|inout)\b"
        r"(?:\s+(?:wire|reg|logic))?"
        r"(?:\s*\[[^\]]+\])?"
        r"\s+([^;]+);"
    )

    for match in port_pattern.finditer(text):

        declaration = match.group(1)

        for name in declaration.split(","):

            name = name.strip()

            if name:
                port_names.add(name)

    num_pins = len(port_names)

    # ------------------------------------------------------------
    # Buffers
    # ------------------------------------------------------------

    num_buffers = 0

    for master, instance in cells:

        master_lower = master.lower()

        if (
            "__buf" in master_lower
            or "__clkbuf" in master_lower
            or master_lower.endswith("_buf")
        ):

            num_buffers += 1

    return {
        "num_cells": num_cells if num_cells > 0 else None,
        "num_nets": num_nets if num_nets > 0 else None,
        "num_pins": num_pins if num_pins > 0 else None,
        "num_buffers": num_buffers,
    }


# ================================================================
# Query final OpenROAD database
# ================================================================

def query_odb():

    if not ODB.exists():

        print(
            "[WARNING] final.odb not found."
        )

        return {}

    tcl_script = r'''
read_db "__ODB__"

set block [ord::get_db_block]

# ============================================================
# DBU / micron
# ============================================================

set dbu [$block getDbUnitsPerMicron]

puts "METRIC DBU_PER_MICRON $dbu"

# ============================================================
# DIE AREA
# ============================================================

set die [$block getDieArea]

set die_xmin [$die xMin]
set die_ymin [$die yMin]
set die_xmax [$die xMax]
set die_ymax [$die yMax]

set die_area_dbu2 [expr {
    ($die_xmax - $die_xmin) *
    ($die_ymax - $die_ymin)
}]

set die_area_um2 [expr {
    double($die_area_dbu2) /
    double($dbu * $dbu)
}]

puts "METRIC DIE_AREA_UM2 $die_area_um2"

# ============================================================
# CORE AREA
# ============================================================

set core [$block getCoreArea]

set core_xmin [$core xMin]
set core_ymin [$core yMin]
set core_xmax [$core xMax]
set core_ymax [$core yMax]

set core_area_dbu2 [expr {
    ($core_xmax - $core_xmin) *
    ($core_ymax - $core_ymin)
}]

set core_area_um2 [expr {
    double($core_area_dbu2) /
    double($dbu * $dbu)
}]

puts "METRIC CORE_AREA_UM2 $core_area_um2"

# ============================================================
# INSTANCES
# ============================================================

set insts [$block getInsts]

puts "METRIC NUM_CELLS [llength $insts]"

# ============================================================
# NETS
# ============================================================

set nets [$block getNets]

puts "METRIC NUM_NETS [llength $nets]"

# ============================================================
# PINS
# ============================================================

set pin_count 0

foreach inst $insts {

    set iterms [$inst getITerms]

    set pin_count [expr {
        $pin_count + [llength $iterms]
    }]
}

puts "METRIC NUM_PINS $pin_count"

# ============================================================
# BUFFERS
# ============================================================

set buffer_count 0

foreach inst $insts {

    set master [$inst getMaster]

    if {$master == ""} {
        continue
    }

    set master_name [$master getName]

    set master_lower \
        [string tolower $master_name]

    if {
        [string match "*__buf*" $master_lower] ||
        [string match "*__clkbuf*" $master_lower]
    } {

        incr buffer_count
    }
}

puts "METRIC NUM_BUFFERS $buffer_count"

# ============================================================
# ROUTED NET COUNT
#
# IMPORTANT:
# This is NOT the same as VIA COUNT.
# It is only a diagnostic metric.
# ============================================================

set routed_net_count 0

foreach net $nets {

    set wire [$net getWire]

    if {$wire != ""} {
        incr routed_net_count
    }
}

puts "METRIC ROUTED_NET_COUNT $routed_net_count"

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
                script_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120
        )

        output = result.stdout

    except Exception as exc:

        print(
            f"[WARNING] OpenROAD ODB query failed: {exc}"
        )

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

        value_string = match.group(2)

        try:

            value = float(value_string)

            if value.is_integer():
                value = int(value)

            metrics[key] = value

        except ValueError:
            pass

    return metrics


# ================================================================
# Wirelength report parser
# ================================================================

def extract_wirelength_report():

    candidates = [
        RUN_DIR / "wirelength_final.rpt",
        RUN_DIR / "wirelength_detailed.rpt",
        RUN_DIR / "wirelength_global.rpt",
    ]

    for path in candidates:

        text = read_text(path)

        if not text.strip():
            continue

        patterns = [

            r"\btotal_wl\s+"
            r"([0-9]+(?:\.[0-9]+)?)",

            r"\btotal_wirelength\s+"
            r"([0-9]+(?:\.[0-9]+)?)",

            r"\btotal\s+wirelength\s*[:=]\s*"
            r"([0-9]+(?:\.[0-9]+)?)",
        ]

        value = first_float(
            patterns,
            text
        )

        if value is not None:
            return value

    return None


# ================================================================
# DEF / routing metrics
#
# The previous DEF parser attempted to infer vias from DEF tokens.
# That was not reliable, so VIA_COUNT remains unavailable until
# we implement a proper OpenDB routing-object query.
# ================================================================

def extract_def_routing_metrics():

    text = read_text(DEF)

    return {
        "wirelength_um": None,
        "via_count": None,
    }


# ================================================================
# Congestion
# ================================================================

def extract_congestion():

    path = RUN_DIR / "congestion.rpt"

    text = read_text(path)

    if not text.strip():
        return None

    patterns = [

        r"total\s+overflow\s*[:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)",

        r"overflow\s*[:=]\s*"
        r"([0-9]+(?:\.[0-9]+)?)",

        r"\boverflow\s+"
        r"([0-9]+(?:\.[0-9]+)?)",
    ]

    value = first_float(
        patterns,
        text
    )

    return value


# ================================================================
# Timing
# ================================================================

def extract_timing():

    # ------------------------------------------------------------
    # Setup WNS
    # ------------------------------------------------------------

    setup_wns = first_float(
        [
            r"\bwns\s+"
            r"(-?[0-9]+(?:\.[0-9]+)?)",

            r"wns\s*[:=]\s*"
            r"(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(
            RUN_DIR / "wns_setup.rpt"
        )
    )

    # ------------------------------------------------------------
    # Setup TNS
    # ------------------------------------------------------------

    setup_tns = first_float(
        [
            r"\btns\s+"
            r"(-?[0-9]+(?:\.[0-9]+)?)",

            r"tns\s*[:=]\s*"
            r"(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(
            RUN_DIR / "tns_setup.rpt"
        )
    )

    # ------------------------------------------------------------
    # Hold WNS
    #
    # Do not depend on wns_hold.rpt because it may be empty.
    # Find every slack in timing_hold.rpt and take the minimum.
    # ------------------------------------------------------------

    hold_text = read_text(
        RUN_DIR / "timing_hold.rpt"
    )

    hold_slacks = re.findall(
        r"(-?[0-9]+(?:\.[0-9]+)?)"
        r"\s+slack\s+"
        r"\((?:MET|VIOLATED)\)",
        hold_text,
        re.IGNORECASE
    )

    hold_wns = None

    if hold_slacks:

        hold_wns = min(
            float(value)
            for value in hold_slacks
        )

    # ------------------------------------------------------------
    # Hold TNS
    # ------------------------------------------------------------

    hold_tns = first_float(
        [
            r"\btns\s+"
            r"(-?[0-9]+(?:\.[0-9]+)?)",

            r"tns\s*[:=]\s*"
            r"(-?[0-9]+(?:\.[0-9]+)?)",
        ],
        read_text(
            RUN_DIR / "tns_hold.rpt"
        )
    )

    if hold_tns is None and hold_slacks:

        negative_slacks = [

            float(value)

            for value in hold_slacks

            if float(value) < 0
        ]

        if negative_slacks:

            hold_tns = sum(
                negative_slacks
            )

        else:

            hold_tns = 0.0

    # ------------------------------------------------------------
    # Convert ns -> ps
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
# Main
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
    # Initialize features
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

        "die_area_um2": None,

        "core_area_um2": None,

        "wirelength_um": None,

        "via_count": None,

        "routing_overflow": None,

        "wns_setup_ps": None,

        "tns_setup_ps": None,

        "wns_hold_ps": None,

        "tns_hold_ps": None,

        "wirelength_available": False,

        "congestion_available": False,

        "timing_available": False,

        "valid_run": False,
    }

    # ------------------------------------------------------------
    # Netlist
    # ------------------------------------------------------------

    netlist_stats = extract_netlist_stats()

    features.update(
        netlist_stats
    )

    # ------------------------------------------------------------
    # ODB
    # ------------------------------------------------------------

    odb_metrics = query_odb()

    if "NUM_CELLS" in odb_metrics:

        features["num_cells"] = \
            odb_metrics["NUM_CELLS"]

    if "NUM_NETS" in odb_metrics:

        features["num_nets"] = \
            odb_metrics["NUM_NETS"]

    if "NUM_PINS" in odb_metrics:

        features["num_pins"] = \
            odb_metrics["NUM_PINS"]

    if "NUM_BUFFERS" in odb_metrics:

        features["num_buffers"] = \
            odb_metrics["NUM_BUFFERS"]

    if "DIE_AREA_UM2" in odb_metrics:

        features["die_area_um2"] = \
            odb_metrics["DIE_AREA_UM2"]

    if "CORE_AREA_UM2" in odb_metrics:

        features["core_area_um2"] = \
            odb_metrics["CORE_AREA_UM2"]

    # ------------------------------------------------------------
    # Wirelength report
    # ------------------------------------------------------------

    wirelength = extract_wirelength_report()

    if wirelength is not None:

        features["wirelength_um"] = \
            wirelength

        features["wirelength_available"] = True

    # ------------------------------------------------------------
    # DEF routing metrics
    #
    # Currently only used as a placeholder.
    # Do not use its via_count as a real via metric.
    # ------------------------------------------------------------

    def_metrics = extract_def_routing_metrics()

    if features["wirelength_um"] is None:

        if def_metrics["wirelength_um"] is not None:

            features["wirelength_um"] = \
                def_metrics["wirelength_um"]

            features["wirelength_available"] = True

    # IMPORTANT:
    # Do NOT assign routed-net count or DEF token count to via_count.
    # A real via-object query will be added separately.

    features["via_count"] = None

    # ------------------------------------------------------------
    # Congestion
    # ------------------------------------------------------------

    congestion = extract_congestion()

    if congestion is not None:

        features["routing_overflow"] = \
            congestion

        features["congestion_available"] = True

    # ------------------------------------------------------------
    # Timing
    # ------------------------------------------------------------

    timing = extract_timing()

    features.update(
        timing
    )

    if (
        timing["wns_setup_ps"] is not None
        and timing["tns_setup_ps"] is not None
        and timing["wns_hold_ps"] is not None
    ):

        features["timing_available"] = True

    # ------------------------------------------------------------
    # ODB existence check
    # ------------------------------------------------------------

    if ODB.exists():

        print(
            "[INFO] final.odb exists."
        )

    else:

        print(
            "[WARNING] final.odb does not exist."
        )

    # ------------------------------------------------------------
    # Final validity
    #
    # A valid ML row requires all required physical, routing,
    # congestion, and timing metrics.
    #
    # Since via_count and routing_overflow are not available yet,
    # valid_run will remain False until those metrics are obtained.
    # ------------------------------------------------------------

    features["valid_run"] = bool(

        ODB.exists()

        and features["num_cells"] is not None

        and features["num_nets"] is not None

        and features["num_pins"] is not None

        and features["num_buffers"] is not None

        and features["die_area_um2"] is not None

        and features["core_area_um2"] is not None

        and features["wirelength_um"] is not None

        and features["via_count"] is not None

        and features["routing_overflow"] is not None

        and features["wns_setup_ps"] is not None

        and features["tns_setup_ps"] is not None

        and features["wns_hold_ps"] is not None
    )

    # ------------------------------------------------------------
    # Save JSON
    # ------------------------------------------------------------

    with OUTPUT.open("w") as f:

        json.dump(
            features,
            f,
            indent=2
        )

    # ------------------------------------------------------------
    # Display
    # ------------------------------------------------------------

    print("=" * 70)
    print("FEATURE EXTRACTION COMPLETE")
    print("=" * 70)

    print(
        f"Output: {OUTPUT}"
    )

    print()

    for key, value in features.items():

        print(
            f"{key:30s}: {value}"
        )


if __name__ == "__main__":
    main()
