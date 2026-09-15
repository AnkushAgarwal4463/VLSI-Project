import os, json
import pandas as pd

runs_dir = "systolic_project/runs"
records = []

if os.path.exists(runs_dir):
    for root, _, files in os.walk(runs_dir):
        for file in files:
            if file.endswith("_features.json"):
                with open(os.path.join(root, file)) as f:
                    data = json.load(f)
                    if "error" not in data:
                        records.append(data)

df = pd.DataFrame(records)
out_csv = "dataset/placement_dataset_real.csv"
os.makedirs("dataset", exist_ok=True)
df.to_csv(out_csv, index=False)
print(f"Dataset aggregated successfully: {len(df)} samples saved to {out_csv}")
