import os
import sys
import json
import math
import csv
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

# Directory containing all sweep runs
RUNS_DIR = Path("systolic_project/runs")

# Final ML dataset
OUTPUT_CSV = Path("systolic_project/summary_output/dataset.csv")


# ============================================================
# FINAL ML DATASET SCHEMA
# ============================================================
#
# 19 ML features:
#
# 1.  array_size
# 2.  data_width
# 3.  utilization
# 4.  clock_period
# 5.  max_density
# 6.  mean_density
# 7.  std_density
# 8.  pin_density
# 9.  avg_fanout
# 10. max_fanout
# 11. x_spread
# 12. y_spread
# 13. num_registers
# 14. logic_depth
# 15. crit_path_wirelength
# 16. estimated_wirelength
# 17. congestion
# 18. WNS
# 19. TNS
#
# run_tag is retained internally for deduplication only.
# ============================================================

FEATURE_COLUMNS = [
    "array_size",
    "data_width",
    "utilization",
    "clock_period",
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

REQUIRED_FIELDS = FEATURE_COLUMNS + ["run_tag"]


# ============================================================
# DIRECTORIES / FILES TO IGNORE
# ============================================================

IGNORED_DIRS = {
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "summary_output",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_number(value):
    """
    Return True only for valid finite numeric values.
    Reject None, strings, NaN and infinity.
    """
    if isinstance(value, bool):
        return False

    if isinstance(value, (int, float)):
        return math.isfinite(float(value))

    return False


def find_feature_files(root_dir):
    """
    Recursively find:
        features.json
        *_features.json

    while ignoring irrelevant directories.
    """

    feature_files = []

    if not root_dir.exists():
        return feature_files

    for current_root, dirs, files in os.walk(root_dir):

        # Prevent traversal into ignored directories
        dirs[:] = [
            d for d in dirs
            if d not in IGNORED_DIRS
        ]

        for filename in files:
            if filename == "features.json" or filename.endswith("_features.json"):
                feature_files.append(
                    Path(current_root) / filename
                )

    return sorted(feature_files)


def load_json(path):
    """
    Load a JSON file safely.
    """

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except json.JSONDecodeError as exc:
        print(
            f"[ERROR] Invalid JSON: {path}\n"
            f"        {exc}"
        )
        return None

    except OSError as exc:
        print(
            f"[ERROR] Could not read: {path}\n"
            f"        {exc}"
        )
        return None


def validate_feature_record(data, path):
    """
    Validate that all required fields exist and contain
    usable values.
    """

    if not isinstance(data, dict):
        print(f"[ERROR] JSON root is not an object: {path}")
        return False

    missing = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            missing.append(field)

    if missing:
        print(
            f"[ERROR] Missing required fields in {path}:\n"
            f"        {', '.join(missing)}"
        )
        return False

    # run_tag must be a non-empty string
    if not isinstance(data["run_tag"], str) or not data["run_tag"].strip():
        print(
            f"[ERROR] Invalid run_tag in {path}"
        )
        return False

    # All ML features must be finite numbers
    invalid = []

    for field in FEATURE_COLUMNS:
        if not is_number(data[field]):
            invalid.append(field)

    if invalid:
        print(
            f"[ERROR] Invalid/non-numeric values in {path}:\n"
            f"        {', '.join(invalid)}"
        )
        return False

    return True


def check_valid_run(data, path):
    """
    Respect the extractor's valid_run flag.

    If valid_run exists and is False, reject the record.

    If the field does not exist, allow the record because
    older feature files may not contain it.
    """

    if "valid_run" in data:

        if data["valid_run"] is False:
            print(
                f"[SKIP] valid_run=False: {path}"
            )
            return False

    return True


def normalize_record(data):
    """
    Extract only the 19 ML columns.

    run_tag is intentionally excluded from the final CSV.
    """

    record = {}

    for field in FEATURE_COLUMNS:
        value = data[field]

        # Store integers as integers where appropriate
        if field in {
            "array_size",
            "data_width",
            "max_fanout",
            "num_registers",
            "logic_depth",
        }:
            record[field] = int(value)

        else:
            record[field] = float(value)

    return record


# ============================================================
# MAIN AGGREGATION
# ============================================================

def main():

    print("=" * 70)
    print("SYSTOLIC ARRAY ML DATASET AGGREGATION")
    print("=" * 70)

    print(f"Runs directory : {RUNS_DIR}")
    print(f"Output CSV     : {OUTPUT_CSV}")
    print()

    # --------------------------------------------------------
    # Check runs directory
    # --------------------------------------------------------

    if not RUNS_DIR.exists():

        print(
            f"[ERROR] Runs directory does not exist:\n"
            f"        {RUNS_DIR}"
        )

        return 1

    # --------------------------------------------------------
    # Find feature files
    # --------------------------------------------------------

    feature_files = find_feature_files(RUNS_DIR)

    print(
        f"[INFO] Feature files found: {len(feature_files)}"
    )
    print()

    if not feature_files:

        print(
            "[ERROR] No feature files were found.\n"
            "        Expected files such as:\n"
            "        systolic_project/runs/<run_tag>/features.json"
        )

        return 1

    # --------------------------------------------------------
    # Load and validate
    # --------------------------------------------------------

    records_by_run_tag = {}

    valid_count = 0
    invalid_count = 0
    skipped_count = 0

    for feature_file in feature_files:

        data = load_json(feature_file)

        if data is None:
            invalid_count += 1
            continue

        # Respect valid_run
        if not check_valid_run(data, feature_file):
            skipped_count += 1
            continue

        # Validate schema
        if not validate_feature_record(data, feature_file):
            invalid_count += 1
            continue

        run_tag = data["run_tag"]

        # ----------------------------------------------------
        # Deduplicate by run_tag
        #
        # If the same run appears more than once, the latest
        # discovered record replaces the previous one.
        # ----------------------------------------------------

        if run_tag in records_by_run_tag:

            print(
                f"[WARNING] Duplicate run_tag detected: "
                f"{run_tag}"
            )

        records_by_run_tag[run_tag] = (
            data,
            feature_file
        )

        valid_count += 1

    # --------------------------------------------------------
    # Safety check
    # --------------------------------------------------------

    if not records_by_run_tag:

        print()
        print("[ERROR] No valid feature records available.")
        print("[ERROR] CSV will NOT be overwritten.")

        return 1

    # --------------------------------------------------------
    # Sort runs deterministically
    # --------------------------------------------------------

    sorted_runs = sorted(
        records_by_run_tag.items(),
        key=lambda item: item[0]
    )

    # --------------------------------------------------------
    # Prepare output directory
    # --------------------------------------------------------

    OUTPUT_CSV.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Write CSV
    # --------------------------------------------------------

    temp_csv = OUTPUT_CSV.with_suffix(".tmp.csv")

    try:

        with open(
            temp_csv,
            "w",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=FEATURE_COLUMNS
            )

            writer.writeheader()

            for run_tag, (data, source_file) in sorted_runs:

                record = normalize_record(data)

                writer.writerow(record)

        # Atomic replacement
        os.replace(
            temp_csv,
            OUTPUT_CSV
        )

    except OSError as exc:

        print(
            f"[ERROR] Failed to write CSV:\n"
            f"        {exc}"
        )

        if temp_csv.exists():
            temp_csv.unlink()

        return 1

    # ========================================================
    # FINAL VERIFICATION
    # ========================================================

    print()
    print("=" * 70)
    print("DATASET VERIFICATION")
    print("=" * 70)

    try:

        with open(
            OUTPUT_CSV,
            "r",
            newline="",
            encoding="utf-8"
        ) as f:

            reader = csv.DictReader(f)

            actual_columns = reader.fieldnames or []

            rows = list(reader)

    except OSError as exc:

        print(
            f"[ERROR] Could not verify CSV:\n"
            f"        {exc}"
        )

        return 1

    # --------------------------------------------------------
    # Verify columns
    # --------------------------------------------------------

    if actual_columns != FEATURE_COLUMNS:

        print("[ERROR] CSV schema mismatch!")
        print()
        print("Expected:")
        print(FEATURE_COLUMNS)
        print()
        print("Actual:")
        print(actual_columns)

        return 1

    # --------------------------------------------------------
    # Verify row count
    # --------------------------------------------------------

    if len(rows) == 0:

        print(
            "[ERROR] CSV contains zero rows."
        )

        return 1

    # --------------------------------------------------------
    # Verify every value
    # --------------------------------------------------------

    invalid_cells = []

    for row_index, row in enumerate(rows, start=2):

        for field in FEATURE_COLUMNS:

            value = row.get(field)

            if value is None or value == "":

                invalid_cells.append(
                    f"row {row_index}, column {field}"
                )
                continue

            try:

                numeric_value = float(value)

                if not math.isfinite(numeric_value):

                    invalid_cells.append(
                        f"row {row_index}, column {field}"
                    )

            except ValueError:

                invalid_cells.append(
                    f"row {row_index}, column {field}"
                )

    if invalid_cells:

        print("[ERROR] Invalid CSV values detected:")

        for item in invalid_cells[:20]:
            print(f"        {item}")

        if len(invalid_cells) > 20:
            print(
                f"        ... and "
                f"{len(invalid_cells) - 20} more"
            )

        return 1

    # ========================================================
    # SUCCESS SUMMARY
    # ========================================================

    print()
    print(f"CSV output       : {OUTPUT_CSV}")
    print(f"Rows             : {len(rows)}")
    print(f"Columns          : {len(actual_columns)}")
    print(f"Valid files      : {valid_count}")
    print(f"Skipped files    : {skipped_count}")
    print(f"Invalid files    : {invalid_count}")
    print()

    print("FINAL ML COLUMNS:")
    print("-" * 70)

    for index, column in enumerate(FEATURE_COLUMNS, start=1):

        print(
            f"{index:2d}. {column}"
        )

    print()
    print("=" * 70)
    print("DATASET AGGREGATION SUCCESSFUL")
    print("=" * 70)

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
