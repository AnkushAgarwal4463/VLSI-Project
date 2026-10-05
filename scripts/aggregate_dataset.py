import os
import glob
import json
import pandas as pd


# ================================================================
# DATASET SCHEMA
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
    "wns_hold_ps": 0.0,
}

FEATURE_COLUMNS = list(SCHEMA_DEFAULTS.keys())


# ================================================================
# FIELD ALIASES
#
# These map the names produced by extract_features.py to the
# names required by the final CSV.
# ================================================================

FIELD_ALIASES = {

    "run_tag": [
        "run_tag"
    ],

    "array_size": [
        "array_size"
    ],

    "data_width": [
        "data_width"
    ],

    "utilization": [
        "utilization"
    ],

    "clk_period_ns": [
        "clock_period",
        "clk_period_ns",
        "clk_period"
    ],

    "num_cells": [
        "num_cells"
    ],

    "num_nets": [
        "num_nets"
    ],

    "num_pins": [
        "num_pins"
    ],

    "num_buffers": [
        "num_buffers"
    ],

    "die_area_u2": [
        "die_area_um2",
        "die_area_u2",
        "die_area"
    ],

    "core_area_u2": [
        "core_area_um2",
        "core_area_u2",
        "core_area"
    ],

    "wirelength_u": [
        "wirelength_um",
        "wirelength_u"
    ],

    "via_count": [
        "via_count"
    ],

    "congestion_overflow_pct": [
        "congestion",
        "congestion_overflow_pct"
    ],

    "wns_setup_ps": [
        "WNS",
        "wns_setup_ps",
        "wns_setup"
    ],

    "tns_setup_ps": [
        "TNS",
        "tns_setup_ps",
        "tns_setup"
    ],

    "wns_hold_ps": [
        "hold_WNS",
        "wns_hold_ps",
        "wns_hold"
    ],
}


# ================================================================
# REQUIRED PHYSICAL-DESIGN FEATURES
#
# A run should not silently become a valid dataset row if the
# actual routing/timing data is missing.
# ================================================================

REQUIRED_SOURCE_FIELDS = [
    "array_size",
    "data_width",
    "utilization",
    "num_cells",
    "num_nets",
    "num_pins",
    "num_buffers",
    "via_count",
    "wirelength_um",
    "congestion",
    "WNS",
    "TNS",
    "hold_WNS",
]


# ================================================================
# TYPE CONVERSION
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
# GET VALUE USING ALIASES
# ================================================================

def get_alias_value(data, output_key):

    aliases = FIELD_ALIASES.get(
        output_key,
        [output_key]
    )

    for key in aliases:

        if key in data and data[key] is not None:
            return data[key]

    return None


# ================================================================
# FIND FEATURE JSON FILES
# ================================================================

def find_feature_files():

    search_roots = [
        "systolic_project/runs",
        "runs",
        "."
    ]

    patterns = [
        "**/features.json",
        "**/*_features.json"
    ]

    found = set()

    ignored_dirs = {
        ".git",
        ".github",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        "summary_output",
    }

    for root in search_roots:

        if not os.path.exists(root):
            continue

        for pattern in patterns:

            full_pattern = os.path.join(
                root,
                pattern
            )

            for path in glob.glob(
                full_pattern,
                recursive=True
            ):

                normalized = os.path.normpath(path)

                parts = normalized.split(os.sep)

                if any(
                    part in ignored_dirs
                    for part in parts
                ):
                    continue

                if os.path.isfile(normalized):
                    found.add(normalized)

    return sorted(found)


# ================================================================
# VALIDATE SOURCE JSON
# ================================================================

def validate_source_data(data, fpath):

    missing = []

    for key in REQUIRED_SOURCE_FIELDS:

        if key not in data:
            missing.append(key)
            continue

        if data[key] is None:
            missing.append(key)

    if missing:

        print(
            f"[WARNING] Invalid/incomplete run:"
            f" {fpath}"
        )

        print(
            f"         Missing required source fields: "
            f"{missing}"
        )

        return False

    # ------------------------------------------------------------
    # Respect valid_run from extractor.
    #
    # Do NOT turn an invalid physical-design run into a valid
    # dataset row merely because defaults exist.
    # ------------------------------------------------------------

    if "valid_run" in data:

        if data["valid_run"] is not True:

            print(
                f"[WARNING] Skipping invalid run: "
                f"{data.get('run_tag', fpath)}"
            )

            missing_required = data.get(
                "missing_required_features",
                []
            )

            if missing_required:
                print(
                    f"         Missing: "
                    f"{missing_required}"
                )

            return False

    return True


# ================================================================
# BUILD CLEAN RECORD
# ================================================================

def make_clean_record(data):

    record = {}

    for output_key, default_value in SCHEMA_DEFAULTS.items():

        value = get_alias_value(
            data,
            output_key
        )

        record[output_key] = clean_value(
            value,
            default_value
        )

    return record


# ================================================================
# MAIN AGGREGATION FUNCTION
# ================================================================

def build_clean_dataset(
    output_csv="summary_output/systolic_array_sweep_dataset.csv"
):

    print("=" * 70)
    print("SYSTOLIC ARRAY DATASET AGGREGATION")
    print("=" * 70)

    print()
    print("[INFO] Searching workspace for feature JSON files...")

    json_files = find_feature_files()

    print(
        f"[INFO] Found {len(json_files)} feature JSON files"
    )

    if not json_files:

        print()
        print(
            "[ERROR] No feature JSON files were found."
        )

        print(
            "[ERROR] CSV will NOT be overwritten with an empty dataset."
        )

        print()
        print(
            "[ERROR] Expected files such as:"
        )

        print(
            "        */features.json"
        )

        print(
            "        */*_features.json"
        )

        return False

    print()

    # ============================================================
    # READ FEATURE FILES
    # ============================================================

    seen_tags = set()
    records = []

    invalid_count = 0
    duplicate_count = 0
    parse_error_count = 0

    for fpath in json_files:

        try:

            with open(
                fpath,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

        except json.JSONDecodeError as e:

            print(
                f"[WARNING] Invalid JSON: {fpath}"
            )

            print(
                f"          {e}"
            )

            parse_error_count += 1

            continue

        except Exception as e:

            print(
                f"[WARNING] Could not read: {fpath}"
            )

            print(
                f"          {e}"
            )

            parse_error_count += 1

            continue

        if not isinstance(data, dict):

            print(
                f"[WARNING] JSON is not an object: "
                f"{fpath}"
            )

            invalid_count += 1

            continue

        # --------------------------------------------------------
        # Determine run tag
        # --------------------------------------------------------

        tag = data.get("run_tag")

        if not tag:

            parent_dir = os.path.basename(
                os.path.dirname(fpath)
            )

            if parent_dir:
                tag = parent_dir

        if not tag:

            print(
                f"[WARNING] No run_tag found: "
                f"{fpath}"
            )

            invalid_count += 1

            continue

        # --------------------------------------------------------
        # Validate actual extracted features
        # --------------------------------------------------------

        if not validate_source_data(
            data,
            fpath
        ):

            invalid_count += 1

            continue

        # --------------------------------------------------------
        # Deduplicate
        # --------------------------------------------------------

        if tag in seen_tags:

            print(
                f"[WARNING] Duplicate run_tag skipped: "
                f"{tag}"
            )

            print(
                f"          File: {fpath}"
            )

            duplicate_count += 1

            continue

        seen_tags.add(tag)

        # --------------------------------------------------------
        # Build clean CSV record
        # --------------------------------------------------------

        clean_record = make_clean_record(
            data
        )

        records.append(
            clean_record
        )

        print(
            f"[OK] {tag}"
        )

    # ============================================================
    # SAFETY CHECK
    # ============================================================

    if not records:

        print()
        print(
            "[ERROR] Zero valid feature records were found."
        )

        print(
            "[ERROR] Existing CSV will NOT be overwritten."
        )

        return False

    # ============================================================
    # DATAFRAME
    # ============================================================

    df = pd.DataFrame(
        records
    )

    # Guarantee exact column order

    df = df[
        FEATURE_COLUMNS
    ]

    # ============================================================
    # NUMERIC COLUMNS
    # ============================================================

    numeric_columns = [
        "array_size",
        "data_width",
        "utilization",
        "clk_period_ns",
        "num_cells",
        "num_nets",
        "num_pins",
        "num_buffers",
        "die_area_u2",
        "core_area_u2",
        "wirelength_u",
        "via_count",
        "congestion_overflow_pct",
        "wns_setup_ps",
        "tns_setup_ps",
        "wns_hold_ps",
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # ============================================================
    # SORT
    # ============================================================

    sort_cols = [
        "array_size",
        "data_width",
        "utilization",
        "clk_period_ns",
    ]

    df = df.sort_values(
        by=sort_cols,
        kind="stable"
    ).reset_index(
        drop=True
    )

    # ============================================================
    # OUTPUT DIRECTORY
    # ============================================================

    output_dir = os.path.dirname(
        output_csv
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

    # ============================================================
    # WRITE CSV
    # ============================================================

    df.to_csv(
        output_csv,
        index=False
    )

    # ============================================================
    # FINAL VALIDATION
    # ============================================================

    print()
    print("=" * 70)
    print("DATASET SUMMARY")
    print("=" * 70)

    print(
        f"Records              : {len(df)}"
    )

    print(
        f"Features             : {len(FEATURE_COLUMNS)}"
    )

    print(
        f"JSON files discovered: {len(json_files)}"
    )

    print(
        f"Valid records        : {len(records)}"
    )

    print(
        f"Invalid records      : {invalid_count}"
    )

    print(
        f"Duplicates skipped   : {duplicate_count}"
    )

    print(
        f"JSON parse errors    : {parse_error_count}"
    )

    print(
        f"Output               : {output_csv}"
    )

    # ============================================================
    # DESIGN SPACE COVERAGE
    # ============================================================

    print()
    print("Design-space coverage:")

    print(
        f"  Array sizes  : "
        f"{sorted(df['array_size'].unique().tolist())}"
    )

    print(
        f"  Data widths  : "
        f"{sorted(df['data_width'].unique().tolist())}"
    )

    print(
        f"  Utilization  : "
        f"{sorted(df['utilization'].unique().tolist())}"
    )

    print(
        f"  Clock periods: "
        f"{sorted(df['clk_period_ns'].unique().tolist())}"
    )

    # ============================================================
    # FINAL SANITY CHECKS
    # ============================================================

    print()
    print("Dataset sanity checks:")

    required_csv_columns = [
        "run_tag",
        "array_size",
        "data_width",
        "utilization",
        "clk_period_ns",
        "wirelength_u",
        "via_count",
        "congestion_overflow_pct",
        "wns_setup_ps",
        "tns_setup_ps",
        "wns_hold_ps",
    ]

    missing_columns = [
        col
        for col in required_csv_columns
        if col not in df.columns
    ]

    if missing_columns:

        print(
            f"[ERROR] Missing CSV columns: "
            f"{missing_columns}"
        )

        return False

    if df["wirelength_u"].isna().any():

        print(
            "[ERROR] Some wirelength values are NaN."
        )

        return False

    if df["via_count"].isna().any():

        print(
            "[ERROR] Some via counts are NaN."
        )

        return False

    print(
        "[OK] All required CSV columns present."
    )

    print(
        "[OK] Wirelength values populated."
    )

    print(
        "[OK] Via counts populated."
    )

    print()
    print("=" * 70)
    print(
        f"[SUCCESS] Written {len(df)} valid records "
        f"across {len(FEATURE_COLUMNS)} features."
    )
    print("=" * 70)

    return True


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":

    success = build_clean_dataset()

    if not success:

        raise SystemExit(1)
