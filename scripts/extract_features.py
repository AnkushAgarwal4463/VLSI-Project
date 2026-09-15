import odb, sys, re, json, os

def extract(run_dir, run_tag, util, clk_period, array_size, data_width):
    odb_path = f"{run_dir}/final.odb"
    if not os.path.exists(odb_path):
        print(json.dumps({"error": f"final.odb not found", "run_tag": run_tag}))
        sys.exit(1)

    db = odb.dbDatabase.create()
    odb.read_db(db, odb_path)
    block = db.getChip().getBlock()
    insts = block.getInsts()
    total_cells = len(insts)

    xs, ys, areas = [], [], []
    for inst in insts:
        bbox = inst.getBBox()
        xs.append((bbox.xMin()+bbox.xMax())/2.0)
        ys.append((bbox.yMin()+bbox.yMax())/2.0)
        areas.append((bbox.xMax()-bbox.xMin())*(bbox.yMax()-bbox.yMin()))

    import numpy as np
    xs, ys, areas = np.array(xs), np.array(ys), np.array(areas)
    x_spread = float(xs.std()) if len(xs) else 0.0
    y_spread = float(ys.std()) if len(ys) else 0.0

    nets = block.getNets()
    fanouts = [len(n.getITerms())-1 for n in nets if len(n.getITerms()) > 1]
    avg_fanout = float(np.mean(fanouts)) if fanouts else 0.0
    max_fanout = float(np.max(fanouts)) if fanouts else 0.0

    core = block.getCoreArea()
    core_area = (core.xMax()-core.xMin()) * (core.yMax()-core.yMin())
    total_cell_area = float(areas.sum())

    max_overflow, mean_overflow, overflow_tiles = 0.0, 0.0, 0
    try:
        with open(f"{run_dir}/congestion.rpt") as f:
            overflows = [float(m.group(1)) for line in f
                         if (m := re.search(r'overflow[:\s]+([0-9.]+)', line, re.IGNORECASE))]
            if overflows:
                max_overflow = max(overflows)
                mean_overflow = sum(overflows)/len(overflows)
                overflow_tiles = sum(1 for o in overflows if o > 0)
    except FileNotFoundError:
        pass

    wns, tns, num_viol = 0.0, 0.0, 0
    try:
        with open(f"{run_dir}/../{run_tag}_log.txt") as f:
            log = f.read()
            wns_m = re.findall(r'worst slack[:\s]+(-?[0-9.]+)', log, re.IGNORECASE)
            tns_m = re.findall(r'tns[:\s]+(-?[0-9.]+)', log, re.IGNORECASE)
            if wns_m: wns = float(wns_m[-1])
            if tns_m: tns = float(tns_m[-1])
            num_viol = len(re.findall(r'VIOLATED', log))
    except FileNotFoundError:
        pass

    return {
        "run_tag": run_tag, "array_size": array_size, "data_width": data_width,
        "utilization": util, "clk_period_ns": clk_period,
        "total_cells": total_cells, "avg_fanout": avg_fanout, "max_fanout": max_fanout,
        "x_spread": x_spread, "y_spread": y_spread,
        "total_cell_area": total_cell_area, "core_area": core_area,
        "max_overflow": max_overflow, "mean_overflow": mean_overflow,
        "overflow_tile_count": overflow_tiles,
        "wns": wns, "tns": tns, "num_viol_paths": num_viol
    }

if __name__ == "__main__":
    run_dir, run_tag = sys.argv[1], sys.argv[2]
    util, clk = float(sys.argv[3]), float(sys.argv[4])
    array_size, data_width = int(sys.argv[5]), int(sys.argv[6])
    row = extract(run_dir, run_tag, util, clk, array_size, data_width)
    print(json.dumps(row))
