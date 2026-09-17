import odb, sys, re, json, os, math

def std_dev(vals):
    if not vals: 
        return 0.0
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((x - mean) ** 2 for x in vals) / len(vals))

def extract(run_dir, run_tag, util, clk_period, array_size, data_width):
    odb_path = os.path.join(run_dir, "final.odb")
    if not os.path.exists(odb_path):
        return {"error": f"final.odb not found", "run_tag": run_tag}

    db = odb.dbDatabase.create()
    odb.read_db(db, odb_path)
    block = db.getChip().getBlock()
    insts = block.getInsts()
    total_cells = len(insts)

    xs, ys, areas = [], [], []
    ff_count, buf_count, high_drive_count = 0, 0, 0
    for inst in insts:
        bbox = inst.getBBox()
        
        # Center coordinates and area evaluation
        cx = (bbox.xMin() + bbox.xMax()) / 2.0
        cy = (bbox.yMin() + bbox.yMax()) / 2.0
        area = (bbox.xMax() - bbox.xMin()) * (bbox.yMax() - bbox.yMin())
        
        xs.append(cx)
        ys.append(cy)
        areas.append(area)

        master_name = inst.getMaster().getName().lower()
        if "dfxtp" in master_name or "dfrtp" in master_name or "flop" in master_name:
            ff_count += 1
        if "buf" in master_name:
            buf_count += 1
        if re.search(r"_[48]$", master_name):
            high_drive_count += 1

    x_spread = std_dev(xs)
    y_spread = std_dev(ys)

    # Calculate net fanouts
    nets = block.getNets()
    fanouts = [len(n.getITerms()) - 1 for n in nets if len(n.getITerms()) > 1]
    avg_fanout = float(sum(fanouts) / len(fanouts)) if fanouts else 0.0
    max_fanout = float(max(fanouts)) if fanouts else 0.0

    # Calculate spatial tile densities with clamp safety
    core = block.getCoreArea()
    core_area = max((core.xMax() - core.xMin()) * (core.yMax() - core.yMin()), 1)
    total_cell_area = float(sum(areas))
    mean_density = 100.0 * total_cell_area / core_area
    pin_density = float(len(block.getBTerms())) / core_area

    GRID = 8
    x0, x1 = core.xMin(), core.xMax()
    y0, y1 = core.yMin(), core.yMax()
    tile_w = max((x1 - x0) / GRID, 1.0)
    tile_h = max((y1 - y0) / GRID, 1.0)
    
    tile_area = [[0.0] * GRID for _ in range(GRID)]
    for inst in insts:
        bbox = inst.getBBox()
        cx = (bbox.xMin() + bbox.xMax()) / 2.0 - x0
        cy = (bbox.yMin() + bbox.yMax()) / 2.0 - y0
        
        # Clamp bounds [0, GRID-1] to prevent out-of-range indices
        gx = max(0, min(int(cx / tile_w), GRID - 1))
        gy = max(0, min(int(cy / tile_h), GRID - 1))
        tile_area[gy][gx] += (bbox.xMax() - bbox.xMin()) * (bbox.yMax() - bbox.yMin())
        
    tile_density = [100.0 * tile_area[i][j] / (tile_w * tile_h) for i in range(GRID) for j in range(GRID)]
    max_density = max(tile_density) if tile_density else 0.0
    std_density = std_dev(tile_density)

    # Extract congestion details
    max_overflow, mean_overflow, overflow_tiles = 0.0, 0.0, 0
    congestion_file = os.path.join(run_dir, "congestion.rpt")
    if os.path.exists(congestion_file):
        with open(congestion_file, "r") as f:
            overflows = [float(m.group(1)) for line in f if (m := re.search(r'overflow[:\s]+([0-9.]+)', line, re.IGNORECASE))]
            if overflows:
                max_overflow = max(overflows)
                mean_overflow = sum(overflows) / len(overflows)
                overflow_tiles = sum(1 for o in overflows if o > 0)

    # Parse timing details safely across OpenROAD output patterns
    wns, tns, num_viol = 0.0, 0.0, 0
    log_file = os.path.join(run_dir, f"openroad.log")
    if not os.path.exists(log_file):
        # Fallback search for general execution logs
        log_file = os.path.join(run_dir, "..", f"{run_tag}_log.txt")

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            log_text = f.read()
            wns_matches = re.findall(r'(?:worst slack|wns)[:\s]+(-?[0-9.]+)', log_text, re.IGNORECASE)
            tns_matches = re.findall(r'tns[:\s]+(-?[0-9.]+)', log_text, re.IGNORECASE)
            if wns_matches: 
                wns = float(wns_matches[-1])
            if tns_matches: 
                tns = float(tns_matches[-1])
            num_viol = len(re.findall(r'VIOLATED', log_text))

    return {
        "run_tag": run_tag, 
        "array_size": array_size, 
        "data_width": data_width,
        "utilization": util, 
        "clk_period_ns": clk_period,
        "total_cells": total_cells, 
        "num_registers": ff_count, 
        "buffer_count": buf_count,
        "high_drive_pct": 100.0 * high_drive_count / max(total_cells, 1),
        "max_density": max_density, 
        "mean_density": mean_density, 
        "std_density": std_density,
        "pin_density": pin_density,
        "avg_fanout": avg_fanout, 
        "max_fanout": max_fanout,
        "x_spread": x_spread, 
        "y_spread": y_spread,
        "total_cell_area": total_cell_area, 
        "core_area": core_area,
        "max_overflow": max_overflow, 
        "mean_overflow": mean_overflow,
        "overflow_tile_count": overflow_tiles,
        "wns": wns, 
        "tns": tns, 
        "num_viol_paths": num_viol,
        "logic_depth": None, 
        "crit_path_wirelength": None
    }

if __name__ == "__main__":
    run_dir = os.environ.get("RUN_DIR", "systolic_project/runs/run_test")
    run_tag = os.environ.get("RUN_TAG", "run_test")
    util = float(os.environ.get("UTIL", "50"))
    clk = float(os.environ.get("CLK_PERIOD", "10.0"))
    array_size = int(os.environ.get("ARRAY_SIZE", "4"))
    data_width = int(os.environ.get("DATA_WIDTH", "8"))

    row = extract(run_dir, run_tag, util, clk, array_size, data_width)
    
    # Save output directly to file to prevent log interference
    out_json_path = os.path.join(run_dir, f"{run_tag}_features.json")
    os.makedirs(run_dir, exist_ok=True)
    with open(out_json_path, "w") as f:
        json.dump(row, f, indent=2)

    # Verification check
    if os.path.exists(out_json_path):
        print(f"[SUCCESS] Extracted features saved to {out_json_path}")
    else:
        print(f"[ERROR] Failed to output JSON for {run_tag}")
