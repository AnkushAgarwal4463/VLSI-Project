import os
import glob
import json
import pandas as pd

# ================================================================
# Dataset schema
# ================================================================

SCHEMA_DEFAULTS = {
    "run_tag": "unknown",
    "array_size": 0,
    "data_width": 0,
    "utilization": 0.0,
    "clk_period_ns": 0.0,
    "num_cells": 0,
    "num_nets": 0,
    "num_pins": 0,
    "num_buffers": 0,
    "die_area_u2": 0.0,
    "core_area_u2": 0.0,
    "wirelength_u": 0.0,
    "via_count": 0,
    "congestion_overflow_pct": 0.0,
    "wns_setup_ps": 0.0,
    "tns_setup_ps": 0.0,
    "wns_hold_ps": 0.0
}

FEATURE_COLUMNS = list(SCHEMA_DEFAULTS.keys())


# ================================================================
# Helper: convert values to expected types
# ================================================================

def clean_value(value, default):
    if value is None:
        return default

    try:
        if isinstance(default, float):
            return float(value)

        if isinstance(default, int):
            return int(value)

        return str(value)

    except (ValueError, TypeError):
        return default


# ================================================================
# Main aggregation function
# ================================================================

def build_clean_dataset(
    runs_dir="systolic_project/runs",
    output_csv="summary_output/systolic_array_sweep_dataset.csv"
):

    print("=" * 70)
    print("SYSTOLIC ARRAY DATASET AGGREGATION")
    print("=" * 70)

    print(f"[INFO] Scanning: {runs_dir}")

    # ------------------------------------------------------------
    # Find BOTH possible JSON naming conventions:
    #
    # 1. Old format:
    #       runs/run_tag_features.json
    #
    # 2. New format:
    #       runs/run_tag/features.json
    # ------------------------------------------------------------

    patterns = [
        os.path.join(runs_dir, "**", "*_features.json"),
        os.path.join(runs_dir, "**", "features.json")
    ]

    json_files = set()

    for pattern in patterns:
        json_files.update(
            glob.glob(pattern, recursive=True)
        )

    json_files = sorted(json_files)

    print(f"[INFO] Found {len(json_files)} feature JSON files")

    # ------------------------------------------------------------
    # Read feature files
    # ------------------------------------------------------------

    seen_tags = set()
    records = []

    for fpath in json_files:

        try:
            with open(fpath, "r") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                print(f"[WARNING] Invalid JSON structure: {fpath}")
                continue

            # ----------------------------------------------------
            # Determine run tag
            # ----------------------------------------------------

            tag = data.get("run_tag")

            if not tag:
                # Try deriving it from the directory name
                parent_dir = os.path.basename(
                    os.path.dirname(fpath)
                )

                if parent_dir:
                    tag = parent_dir

            if not tag:
                print(f"[WARNING] No run_tag found: {fpath}")
                continue

            # ----------------------------------------------------
            # Deduplicate
            # ----------------------------------------------------

            if tag in seen_tags:
                print(
                    f"[WARNING] Duplicate run_tag '{tag}' skipped: "
                    f"{fpath}"
                )
                continue

            seen_tags.add(tag)

            # ----------------------------------------------------
            # Build clean record
            # ----------------------------------------------------

            clean_record = {}

            for key, default_value in SCHEMA_DEFAULTS.items():

                value = data.get(key)

                clean_record[key] = clean_value(
                    value,
                    default_value
                )

            records.append(clean_record)

            print(
                f"[OK] {tag}"
            )

        except json.JSONDecodeError as e:

            print(
                f"[WARNING] Invalid JSON in {fpath}: {e}"
            )

        except Exception as e:

            print(
                f"[WARNING] Could not parse {fpath}: {e}"
            )

    # ------------------------------------------------------------
    # Build DataFrame
    # ------------------------------------------------------------

    if records:

        df = pd.DataFrame(records)

        # Guarantee column order
        df = df[FEATURE_COLUMNS]

        # --------------------------------------------------------
        # Sort according to design-space parameters
        # --------------------------------------------------------

        sort_cols = [
            "array_size",
            "data_width",
            "utilization",
            "clk_period_ns"
        ]

        df = df.sort_values(
            by=sort_cols,
            kind="stable"
        ).reset_index(drop=True)

    else:

        print(
            "[WARNING] No feature JSON files were found."
        )

        df = pd.DataFrame(
            columns=FEATURE_COLUMNS
        )

    # ------------------------------------------------------------
    # Create output directory
    # ------------------------------------------------------------

    output_dir = os.path.dirname(output_csv)

    if output_dir:
        os.makedirs(
            output_dir,
            exist_ok=True
        )

    # ------------------------------------------------------------
    # Write CSV
    # ------------------------------------------------------------

    df.to_csv(
        output_csv,
        index=False
    )

    # ------------------------------------------------------------
    # Dataset summary
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("DATASET SUMMARY")
    print("=" * 70)

    print(f"Records       : {len(df)}")
    print(f"Features      : {len(FEATURE_COLUMNS)}")
    print(f"Output        : {output_csv}")

    if len(df) > 0:

        print()
        print("Design-space coverage:")

        print(
            f"  Array sizes : "
            f"{sorted(df['array_size'].unique().tolist())}"
        )

        print(
            f"  Data widths : "
            f"{sorted(df['data_width'].unique().tolist())}"
        )

        print(
            f"  Utilization : "
            f"{sorted(df['utilization'].unique().tolist())}"
        )

        print(
            f"  Clock periods: "
            f"{sorted(df['clk_period_ns'].unique().tolist())}"
        )

    print("=" * 70)
    print(
        f"[SUCCESS] Written {len(df)} records "
        f"across {len(FEATURE_COLUMNS)} features"
    )


# ================================================================
# Entry point
# ================================================================

if __name__ == "__main__":
    build_clean_dataset()
