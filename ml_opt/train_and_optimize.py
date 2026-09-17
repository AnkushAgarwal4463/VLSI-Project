import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import r2_score
import optuna
import os

# 1. Load Dataset (Support master_summary.csv or dataset fallback)
csv_path = "master_summary.csv" if os.path.exists("master_summary.csv") else "dataset/placement_dataset_real.csv"
df = pd.read_csv(csv_path)

# Remove unused/null columns if present
df = df.drop(columns=['logic_depth', 'crit_path_wirelength', 'error'], errors='ignore').dropna()

# Updated Feature Set including new EDA features
feature_cols = [
    'array_size', 'data_width', 'utilization', 'clk_period_ns',
    'total_cells', 'num_registers', 'buffer_count', 'high_drive_pct',
    'avg_fanout', 'max_fanout', 'x_spread', 'y_spread',
    'max_density', 'mean_density', 'std_density', 'pin_density',
    'total_cell_area', 'core_area'
]

# Ensure all feature columns exist in dataset before splitting
feature_cols = [col for col in feature_cols if col in df.columns]

X = df[feature_cols]
y_cong = df['max_overflow']
y_wns = df['wns']

X_train, X_test, yc_train, yc_test, yw_train, yw_test = train_test_split(
    X, y_cong, y_wns, test_size=0.2, random_state=42
)

# 2. Fit Surrogate Models
rf_cong = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, yc_train)
xgb_wns = XGBRegressor(n_estimators=100, random_state=42).fit(X_train, yw_train)

print(f"Congestion Model R²: {r2_score(yc_test, rf_cong.predict(X_test)):.4f}")
print(f"WNS Timing Model R²:  {r2_score(yw_test, xgb_wns.predict(X_test)):.4f}")

# 3. Multi-Objective Optimization (Optuna NSGA-II)
def objective(trial):
    arr_size = trial.suggest_categorical('array_size', [2, 4, 8])
    width = trial.suggest_categorical('data_width', [8, 16])
    util = trial.suggest_float('utilization', 45.0, 75.0)
    clk = trial.suggest_float('clk_period_ns', 3.0, 10.0)

    # Parametric synthetic estimators for Optuna design point evaluation
    total_cells = (arr_size ** 2) * width * 14
    num_registers = (arr_size ** 2) * width * 4
    buffer_count = int(total_cells * 0.12)
    high_drive_pct = 8.5
    
    total_cell_area = total_cells * 1.5
    core_area = total_cell_area / (util / 100.0)
    side = np.sqrt(core_area)
    
    sample_dict = {
        'array_size': arr_size, 'data_width': width, 'utilization': util,
        'clk_period_ns': clk, 'total_cells': total_cells, 'num_registers': num_registers,
        'buffer_count': buffer_count, 'high_drive_pct': high_drive_pct,
        'avg_fanout': 3.2, 'max_fanout': 16.0, 
        'x_spread': side / 4.0, 'y_spread': side / 4.0,
        'max_density': util + 12.0, 'mean_density': util, 'std_density': 8.5,
        'pin_density': 40.0 / max(core_area, 1.0),
        'total_cell_area': total_cell_area, 'core_area': core_area
    }

    # Filter dictionary to match X_train columns exactly
    sample_df = pd.DataFrame([{k: sample_dict[k] for k in feature_cols}])

    pred_overflow = rf_cong.predict(sample_df)[0]
    pred_wns = xgb_wns.predict(sample_df)[0]

    # Optuna minimizes objectives: minimize overflow, minimize negative WNS (maximize WNS towards >= 0)
    return pred_overflow, -pred_wns

study = optuna.create_study(directions=["minimize", "minimize"], sampler=optuna.samplers.NSGAIISampler())
study.optimize(objective, n_trials=300)

print("\n=== Pareto-Optimal Candidates Found ===")
for trial in study.best_trials:
    print(f"Params: {trial.params} -> Pred Max Overflow: {trial.values[0]:.2f}, Pred WNS: {-trial.values[1]:.2f} ns")
