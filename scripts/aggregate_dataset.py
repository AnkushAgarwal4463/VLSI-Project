import os, json
import pandas as pd

runs_dir = "systolic_project/runs"
records = []

if os.path.exists(runs_dir):
    for root, _, files in os.walk(runs_dir):
        for file in files:
            if file.endswith("_features.json"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r") as f:
                        text = f.read().strip()
                        if not text:
                            continue
                        start_idx = text.find("{")
                        end_idx = text.rfind("}")
                        if start_idx != -1 and end_idx != -1:
                            clean_json = text[start_idx : end_idx + 1]
                            data = json.loads(clean_json)
                            if "error" not in data:
                                records.append(data)
                except Exception as e:
                    print(f"[Warning] Failed to parse {file_path}: {e}")

if records:
    df = pd.DataFrame(records)
    if "run_tag" in df.columns:
        df = df.drop_duplicates(subset=["run_tag"])
    out_csv = "dataset/placement_dataset_real.csv"
    os.makedirs("dataset", exist_ok=True)
    df.to_csv(out_csv, index=False)
    print(f"Dataset aggregated successfully: {len(df)} samples saved to {out_csv}")
else:
    print("[Error] No valid feature JSON files were found to aggregate.")
