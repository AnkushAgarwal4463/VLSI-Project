```python
import os
import glob
import json
import pandas as pd


# ================================================================
# EXACT 17-COLUMN DATASET SCHEMA
# ================================================================
#
# These fields match the current extract_features.py output.
#
# IMPORTANT:
#   - No die area
#   - No core area
#   - No extra diagnostic fields
#   - No renaming of physical-design values
#
# ================================================================

FEATURE_COLUMNS = [
    "array_size",
    "data_width",
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
]


# ================================================================
# REQUIRED FIELDS
# ================================================================
#
# Every valid feature JSON must contain all 17 fields.
#
# run_tag is required for identification but is NOT included
# as one of the 17 ML feature columns.
#
# ================================================================

REQUIRED_FIELDS = [
    "run_tag",
    "array_size",
    "data_width",
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
]


# ================================================================
# NUMERIC COLUMNS
# ================================================================

INTEGER_COLUMNS = [
    "array_size",
    "data_width",
    "max_fanout",
    "num_registers",
    "logic_depth",
]

FLOAT_COLUMNS = [
    "max_density",
    "mean_density",
    "std_density",
    "pin_density",
    "avg_fanout",
    "x_spread",
    "y_spread",
    "crit_path_wirelength",
    "estimated_wirelength",
    "congestion",
    "WNS",
    "TNS",
]


# ================================================================
# FIND FEATURE JSON FILES
# ================================================================

def find_feature_files():

    print("[INFO] Searching recursively for feature JSON files...")

    search_roots = [
        "systolic_project/runs",
        "runs",
        ".",
    ]

    patterns = [
        "**/features.json",
        "**/*_features.json",
    ]

    ignored_dirs = {
        ".git",
        ".github",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "summary_output",
    }

    found_files = set()

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

                path = os.path.normpath(path)

                if not os.path.isfile(path):
                    continue

                parts = path.split(os.sep)

                if any(
                    directory in ignored_dirs
                    for directory in parts
                ):
                    continue

                found_files.add(path)

    return sorted(found_files)


# ================================================================
# VALIDATE FEATURE JSON
# ================================================================

def validate_feature_json(data, filepath):

    # ------------------------------------------------------------
    # JSON must be a dictionary
    # ------------------------------------------------------------

    if not isinstance(data, dict):

        print(
            f"[ERROR] Invalid JSON structure: {filepath}"
        )

        return False


    # ------------------------------------------------------------
    # Check required fields
    # ------------------------------------------------------------

    missing = []

    for field in REQUIRED_FIELDS:

        if field not in data:

            missing.append(field)

        elif data[field] is None:

            missing.append(field)


    if missing:

        print(
            f"[WARNING] Skipping {filepath}"
        )

        print(
            f"         Missing fields: {missing}"
        )

        return False


    # ------------------------------------------------------------
    # Respect valid_run from extractor
    # ------------------------------------------------------------

    if "valid_run" in data:

        if data["valid_run"] is not True:

            print(
                f"[WARNING] Skipping invalid run: "
                f"{data.get('run_tag', filepath)}"
            )

            missing_required = data.get(
                "missing_required_features",
                []
            )

            if missing_required:

                print(
                    f"         Missing required features: "
                    f"{missing_required}"
                )

            return False


    # ------------------------------------------------------------
    # Explicitly verify the 17 values are numeric
    # ------------------------------------------------------------

    for field in INTEGER_COLUMNS:

        try:

            int(data[field])

        except (ValueError, TypeError):

            print(
                f"[WARNING] Non-numeric value for "
                f"{field} in {filepath}"
            )

            return False


    for field in FLOAT_COLUMNS:

        try:

            float(data[field])

        except (ValueError, TypeError):

            print(
                f"[WARNING] Non-numeric value for "
                f"{field} in {filepath}"
            )

            return False


    return True


# ================================================================
# BUILD ONE DATASET RECORD
# ================================================================

def build_record(data):

    record = {}

    # ------------------------------------------------------------
    # Keep run_tag internally for identification.
    # It is NOT part of the final 17 columns.
    # ------------------------------------------------------------

    record["_run_tag"] = str(
        data["run_tag"]
    )


    # ------------------------------------------------------------
    # Copy EXACTLY the 17 requested features
    # ------------------------------------------------------------

    for field in FEATURE_COLUMNS:

        record[field] = data[field]


    return record


# ================================================================
# MAIN AGGREGATION
# ================================================================

def build_clean_dataset(
    output_csv="summary_output/systolic_array_sweep_dataset.csv"
):

    print("=" * 70)
    print("SYSTOLIC ARRAY DATASET AGGREGATION")
    print("=" * 70)

    print()
    print("[INFO] Expected dataset columns:")
    
    for index, column in enumerate(
        FEATURE_COLUMNS,
        start=1
    ):

        print(
            f"  {index:02d}. {column}"
        )


    # ============================================================
    # FIND JSON FILES
    # ============================================================

    json_files = find_feature_files()

    print()
    print(
        f"[INFO] Found {len(json_files)} feature JSON files"
    )


    # ------------------------------------------------------------
    # NEVER overwrite CSV with an empty dataset
    # ------------------------------------------------------------

    if not json_files:

        print()
        print(
            "[ERROR] No feature JSON files found."
        )

        print(
            "[ERROR] Existing CSV will NOT be overwritten."
        )

        return False


    # ============================================================
    # READ JSON FILES
    # ============================================================

    records = []

    seen_tags = set()

    invalid_count = 0
    duplicate_count = 0
    parse_error_count = 0


    print()
    print("[INFO] Processing feature files...")
    print()


    for filepath in json_files:

        # --------------------------------------------------------
        # Read JSON
        # --------------------------------------------------------

        try:

            with open(
                filepath,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)


        except json.JSONDecodeError as error:

            print(
                f"[WARNING] Invalid JSON:"
                f" {filepath}"
            )

            print(
                f"          {error}"
            )

            parse_error_count += 1

            continue


        except Exception as error:

            print(
                f"[WARNING] Could not read:"
                f" {filepath}"
            )

            print(
                f"          {error}"
            )

            parse_error_count += 1

            continue


        # --------------------------------------------------------
        # Validate
        # --------------------------------------------------------

        if not validate_feature_json(
            data,
            filepath
        ):

            invalid_count += 1

            continue


        # --------------------------------------------------------
        # Get run tag
        # --------------------------------------------------------

        run_tag = str(
            data["run_tag"]
        )


        # --------------------------------------------------------
        # Deduplicate
        # --------------------------------------------------------

        if run_tag in seen_tags:

            print(
                f"[WARNING] Duplicate run skipped:"
                f" {run_tag}"
            )

            print(
                f"          File: {filepath}"
            )

            duplicate_count += 1

            continue


        seen_tags.add(run_tag)


        # --------------------------------------------------------
        # Build record
        # --------------------------------------------------------

        record = build_record(
            data
        )

        records.append(
            record
        )


        print(
            f"[OK] {run_tag}"
        )


    # ============================================================
    # FINAL RECORD CHECK
    # ============================================================

    if not records:

        print()
        print(
            "[ERROR] ZERO valid records were found."
        )

        print(
            "[ERROR] Existing CSV will NOT be overwritten."
        )

        return False


    # ============================================================
    # CREATE DATAFRAME
    # ============================================================

    df = pd.DataFrame(
        records
    )


    # ============================================================
    # EXACT COLUMN SELECTION
    # ============================================================
    #
    # This guarantees that the final CSV contains exactly
    # 17 columns and nothing else.
    #
    # ============================================================

    df = df[
        FEATURE_COLUMNS
    ]


    # ============================================================
    # FORCE NUMERIC TYPES
    # ============================================================

    for column in INTEGER_COLUMNS:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        ).astype("Int64")


    for column in FLOAT_COLUMNS:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )


    # ============================================================
    # CHECK FOR NaN
    # ============================================================

    if df.isna().any().any():

        print()
        print(
            "[ERROR] NaN values detected in final dataset."
        )

        print(
            df.isna().sum()
        )

        print(
            "[ERROR] CSV will NOT be written."
        )

        return False


    # ============================================================
    # SORT DATASET
    # ============================================================

    sort_columns = [
        "array_size",
        "data_width",
        "utilization",
        # utilization is NOT in the 17 columns,
        # therefore sorting cannot use it.
    ]

    # ------------------------------------------------------------
    # Since utilization and clock_period are intentionally not
    # part of the 17-column dataset, sort only by the available
    # design dimensions.
    # ------------------------------------------------------------

    sort_columns = [
        "array_size",
        "data_width",
    ]

    df = df.sort_values(
        by=sort_columns,
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
    # VERIFY WRITTEN CSV
    # ============================================================

    if not os.path.exists(output_csv):

        print(
            "[ERROR] CSV file was not created."
        )

        return False


    # Re-read the CSV to verify it.

    verification_df = pd.read_csv(
        output_csv
    )


    if len(
        verification_df.columns
    ) != 17:

        print(
            "[ERROR] Final CSV does not contain exactly "
            "17 columns."
        )

        print(
            f"         Found: "
            f"{len(verification_df.columns)}"
        )

        return False


    if list(
        verification_df.columns
    ) != FEATURE_COLUMNS:

        print(
            "[ERROR] Final CSV column order is incorrect."
        )

        print(
            f"Expected: {FEATURE_COLUMNS}"
        )

        print(
            f"Found:    "
            f"{list(verification_df.columns)}"
        )

        return False


    # ============================================================
    # DATASET SUMMARY
    # ============================================================

    print()
    print("=" * 70)
    print("DATASET SUMMARY")
    print("=" * 70)

    print(
        f"JSON files discovered : {len(json_files)}"
    )

    print(
        f"Valid records         : {len(records)}"
    )

    print(
        f"Invalid records       : {invalid_count}"
    )

    print(
        f"Duplicates skipped    : {duplicate_count}"
    )

    print(
        f"JSON parse errors     : {parse_error_count}"
    )

    print(
        f"Final CSV rows        : {len(verification_df)}"
    )

    print(
        f"Final CSV columns     : "
        f"{len(verification_df.columns)}"
    )

    print(
        f"Output                : {output_csv}"
    )


    # ============================================================
    # DESIGN SPACE COVERAGE
    # ============================================================

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


    # ============================================================
    # FINAL SUCCESS
    # ============================================================

    print()
    print("=" * 70)

    print(
        f"[SUCCESS] Dataset created successfully."
    )

    print(
        f"[SUCCESS] {len(df)} rows × "
        f"{len(df.columns)} columns"
    )

    print(
        "[SUCCESS] Exactly 17 ML features."
    )

    print(
        "[SUCCESS] No die_area_u2."
    )

    print(
        "[SUCCESS] No core_area_u2."
    )

    print(
        "[SUCCESS] No diagnostic columns."
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
```
