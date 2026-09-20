import json
from pathlib import Path
import pandas as pd


def aggregate_dataset():
    runs_dir = Path("systolic_project/runs")
    out_dir = Path("dataset")
    out_csv = out_dir / "placement_dataset_real.csv"

    records = []

    if runs_dir.exists():
        # Glob recursively for ALL json files regardless of exact filename pattern
        json_files = list(runs_dir.rglob("*.json"))
        print(f"[Info] Found {len(json_files)} feature JSON files in {runs_dir}")

        for file_path in json_files:
            try:
                text = file_path.read_text(encoding="utf-8").strip()
                if not text:
                    continue

                # Locate raw JSON boundaries to strip out any stray console logging
                start_idx = text.find("{")
                end_idx = text.rfind("}")

                if start_idx != -1 and end_idx != -1:
                    clean_json = text[start_idx : end_idx + 1]
                    data = json.loads(clean_json)

                    if isinstance(data, dict) and "error" not in data:
                        records.append(data)
                    elif isinstance(data, list):
                        records.extend(data)

            except Exception as e:
                print(f"[Warning] Failed to parse {file_path}: {e}")

    if records:
        df = pd.DataFrame(records)

        # Deduplicate runs based on run_tag if available
        if "run_tag" in df.columns:
            df = df.drop_duplicates(subset=["run_tag"])

        # Prioritize key matrix features on the left side of the CSV
        priority_cols = ["run_tag", "array_size", "data_width", "util", "clk_period"]
        existing_priority = [c for c in priority_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in existing_priority]
        df = df[existing_priority + sorted(other_cols)]

        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
        print(f"[Success] Aggregated {len(df)} samples saved to {out_csv}")
    else:
        print("[Error] No valid feature JSON files were found to aggregate.")


if __name__ == "__main__":
    aggregate_dataset()
