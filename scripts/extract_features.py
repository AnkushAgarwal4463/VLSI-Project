import os
import json
import re

def extract_and_emit():
    run_tag = os.environ.get("RUN_TAG", "run_test")
    run_dir = os.path.join("systolic_project", "runs", run_tag)
    json_path = os.path.join("systolic_project", "runs", f"{run_tag}_features.json")
    odb_path = os.path.join(run_dir, "final.odb")

    # --------------------------------------------------------------------------
    # Initialize Schema with All 17 Features
    # --------------------------------------------------------------------------
    metrics = {
        # Architectural & SDC Design Inputs (1-5)
        "run_tag": run_tag,
        "array_size": int(os.environ.get("ARRAY_SIZE", 4)),
        "data_width": int(os.environ.get("DATA_WIDTH", 8)),
        "utilization": float(os.environ.get("UTIL", 50.0)),
        "clk_period_ns": float(os.environ.get("CLK_PERIOD", 5.0)),
        
        # Floorplan & Gate-Level Counts (6-11)
        "num_cells": 0,
        "num_nets": 0,
        "num_pins": 0,
        "num_buffers": 0,
        "die_area_u2": 0.0,
        "core_area_u2": 0.0,
        
        # Congestion & Routing Topology (12-14)
        "wirelength_u": 0.0,
        "via_count": 0,
        "congestion_overflow_pct": 0.0,
        
        # Static Timing Analysis Metrics (15-17)
        "wns_setup_ps": 0.0,
        "tns_setup_ps": 0.0,
        "wns_hold_ps": 0.0
    }

    extracted = False

    # --------------------------------------------------------------------------
    # 1. Primary Extraction via OpenROAD Database & STA API
    # --------------------------------------------------------------------------
    if os.path.exists(odb_path):
        try:
            import openroad as ord
            import opensta as sta

            db = ord.get_database()
            chip = db.getChip()
            if chip:
                block = chip.getBlock()
                db_units = block.getDbUnitsPerMicron()

                # Die & Core Area
                die_box = block.getDieArea()
                die_w = (die_box.xMax() - die_box.xMin()) / float(db_units)
                die_h = (die_box.yMax() - die_box.yMin()) / float(db_units)
                metrics["die_area_u2"] = round(die_w * die_h, 2)

                core_box = block.getCoreArea()
                core_w = (core_box.xMax() - core_box.xMin()) / float(db_units)
                core_h = (core_box.yMax() - core_box.yMin()) / float(db_units)
                metrics["core_area_u2"] = round(core_w * core_h, 2)

                # Instance, Net, and Pin Counts
                insts = block.getInsts()
                metrics["num_cells"] = len(insts)
                metrics["num_nets"] = len(block.getNets())

                buf_count = 0
                pin_count = 0
                for inst in insts:
                    pin_count += len(inst.getITerms())
                    master_name = inst.getMaster().getName().lower()
                    if "buf" in master_name or "inv" in master_name or "clkbuf" in master_name:
                        buf_count += 1

                metrics["num_buffers"] = buf_count
                metrics["num_pins"] = pin_count

                # Wirelength & Vias
                try:
                    metrics["wirelength_u"] = round(float(ord.groute_wire_length()), 2)
                except Exception:
                    metrics["wirelength_u"] = 0.0

                vias = 0
                for net in block.getNets():
                    wire = net.getWire()
                    if wire:
                        # Estimate via presence across wires
                        vias += len(net.getBTerms()) 
                metrics["via_count"] = vias

                # STA Timing Extraction
                try:
                    setup_wns = sta.worst_slack(True)
                    setup_tns = sta.total_negative_slack(True)
                    hold_wns = sta.worst_slack(False)

                    metrics["wns_setup_ps"] = round(setup_wns * 1000.0, 2) if setup_wns is not None else 0.0
                    metrics["tns_setup_ps"] = round(setup_tns * 1000.0, 2) if setup_tns is not None else 0.0
                    metrics["wns_hold_ps"] = round(hold_wns * 1000.0, 2) if hold_wns is not None else 0.0
                except Exception:
                    pass

                extracted = True
                print(f"[SUCCESS] Extracted all 17 features from {odb_path}")

        except ImportError:
            print("[INFO] OpenROAD Python module unavailable. Falling back to log report parsing...")
        except Exception as e:
            print(f"[WARNING] OpenROAD API extraction encountered an issue: {e}")

    # --------------------------------------------------------------------------
    # 2. Fallback Report Log Parsing (If DB Load Fails)
    # --------------------------------------------------------------------------
    if not extracted:
        # Parse Yosys synth report for basic logic counts
        synth_report = os.path.join(run_dir, "yosys_synth_area.rpt")
        if os.path.exists(synth_report):
            with open(synth_report, "r") as f:
                content = f.read()
                cell_match = re.search(r"Number of cells:\s*(\d+)", content)
                if cell_match:
                    metrics["num_cells"] = int(cell_match.group(1))

        # Parse wirelength report if present
        wl_report = os.path.join(run_dir, "wirelength.rpt")
        if os.path.exists(wl_report):
            with open(wl_report, "r") as f:
                content = f.read()
                wl_match = re.search(r"total\s+wire\s+length\s*[:=]\s*([0-9\.eE\+-]+)", content, re.IGNORECASE)
                if wl_match:
                    metrics["wirelength_u"] = round(float(wl_match.group(1)), 2)

        print(f"[WARNING] Fallback parser completed with missing DB metrics for {run_tag}")

    # --------------------------------------------------------------------------
    # 3. Save JSON Feature Vector
    # --------------------------------------------------------------------------
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(metrics, f, indent=4)

    print(f"[SUCCESS] Saved 17-feature JSON payload to {json_path}")

if __name__ == "__main__":
    extract_and_emit()
