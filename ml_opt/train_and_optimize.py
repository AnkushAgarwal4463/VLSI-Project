import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor
from sklearn.metrics import r2_score, mean_squared_error
import optuna

df = pd.read_csv("dataset/placement_dataset_real.csv")

feature_cols = [
    'array_size', 'data_width', 'utilization', 'clk_period_ns',
    'total_cells', 'avg_fanout', 'max_fanout', 'x_spread', 'y_spread',
    'total_cell_area', 'core_area'
]

X = df[feature_cols]
y_cong = df['max_overflow']
y_wns = df['wns']

X_train, X_test, yc_train, yc_test, yw_train, yw_test = train_test_split(
    X, y_cong, y_wns, test_size=0.2, random_state=42
)

rf_cong = RandomForestRegressor(n_estimators=100, random_state=42).fit(X_train, yc_train)
xgb_wns = XGBRegressor(n_estimators=100, random_state=42).fit(X_train, yw_train)

print(f"Congestion Model R²: {r2_score(yc_test, rf_cong.predict(X_test)):.4f}")
print(f"WNS Timing Model R²:  {r2_score(yw_test, xgb_wns.predict(X_test)):.4f}")

def objective(trial):
    arr_size = trial.suggest_categorical('array_size', [4, 8])
    width = trial.suggest_categorical('data_width', [8, 16])
    util = trial.suggest_float('utilization', 50.0, 90.0)
    clk = trial.suggest_float('clk_period_ns', 2.0, 10.0)

    total_cells = (arr_size ** 2) * width * 12
    total_cell_area = total_cells * 1.5
    core_area = total_cell_area / (util / 100.0)
    
    sample = pd.DataFrame([{
        'array_size': arr_size, 'data_width': width, 'utilization': util,
        'clk_period_ns': clk, 'total_cells': total_cells, 'avg_fanout': 3.2,
        'max_fanout': 16, 'x_spread': np.sqrt(core_area)/4, 'y_spread': np.sqrt(core_area)/4,
        'total_cell_area': total_cell_area, 'core_area': core_area
    }])

    pred_overflow = rf_cong.predict(sample)[0]
    pred_wns = xgb_wns.predict(sample)[0]

    return pred_overflow, -pred_wns

study = optuna.create_study(directions=["minimize", "minimize"], sampler=optuna.samplers.NSGAIISampler())
study.optimize(objective, n_trials=300)

print("\n=== Pareto-Optimal Candidates Found ===")
for trial in study.best_trials:
    print(f"Params: {trial.params} -> Pred Max Overflow: {trial.values[0]:.2f}, Pred WNS: {-trial.values[1]:.2f} ns")
