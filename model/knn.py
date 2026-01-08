import os
import re
import pandas as pd
import numpy as np
import joblib

from collections import defaultdict
from pathlib import Path
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.impute import SimpleImputer

# Add some flags/arguments
CREATE_INTERMEDIATE_DATASET = True
TRAIN = True
EVALUATE = True

DATASET_PATH = "compiled_dataset.csv"
INTERMEDIATE_FILE = "training_dataset_intermediate.csv"

ML_OUTPUTS_DIR = "results"

# Create the directory if it doesn't exist
directory = Path(ML_OUTPUTS_DIR)
directory.mkdir(parents=True, exist_ok=True)

def assign_optimal_resources(df):
    # Group by target request rate and find minimal viable configs
    optimal_configs = {}
    for req_rate, group in df.groupby("request_rate_target"):
        viable = group[
            (group["average_response_time"] < 400) &
            (group["latency_p99"] < 1000) &
            (group["latency_p95"] < 800) &
            (group["success_rate"] >= 0.99) &
            # (group["throttling"] < 0.4) &       # No throttling 0.1
            (group["ram_usage"] <= 70)          # No OOM risk
        ]
        if not viable.empty:
            # Sort by CPU/RAM ascending and pick the smallest viable config
            optimal = viable.sort_values(["cpu_allocated", "ram_allocated"]).iloc[0]
            optimal_configs[req_rate] = (optimal["cpu_allocated"], optimal["ram_allocated"])
    
    # Map optimal values back to the main DataFrame
    df["optimal_cpu"] = df["request_rate_target"].map(lambda x: optimal_configs.get(x, (None, None))[0])
    df["optimal_ram"] = df["request_rate_target"].map(lambda x: optimal_configs.get(x, (None, None))[1])
    
    
    config_groups = defaultdict(list)
    for req_rate, config in optimal_configs.items():
        config_groups[config].append(req_rate)

    # Find and print the largest req_rate for each unique config
    report_path = os.path.join(ML_OUTPUTS_DIR, 'report.txt')
    with open(report_path, 'w') as report_file:
        for config, req_rates in config_groups.items():
            cpu, ram = config
            max_req_rate = max(req_rates)
            message = f"Config (CPU: {cpu}, RAM: {ram}): Largest req_rate = {max_req_rate}"
            
            # Print to console
            print(message)
            
            # Write to file
            report_file.write(message + '\n')

    return df


def parse_stress_result(file_path):
    with open(file_path, 'r') as f:
        text = f.read()
    success = int(re.search(r"Successful requests: (\d+)", text).group(1))
    failed = int(re.search(r"Failed requests: (\d+)", text).group(1))
    return success / (success + failed) if (success + failed) > 0 else 0

def create_intermediate_dataset():
    df = pd.read_csv(DATASET_PATH)

    # Rename columns for clarity
    df.rename(columns={
        "cpu": "cpu_allocated",
        "memory": "ram_allocated",
        "target_rps": "request_rate_target",
        "cpu_per_limit_for_60s": "cpu_usage",
        "memory_per_limit": "ram_usage",
        "request_rate_for_30s": "request_rate_actual",
        "latency_p95": "latency_p95",
        "latency_p99": "latency_p99",
        "cpu_throttling_60s": "throttling",
        "art_for_10s": "average_response_time",
    }, inplace=True)

    df = assign_optimal_resources(df)

    df = df.drop(columns=["Timestamp", "request_rate_target"]) 
    df.to_csv(f"{ML_OUTPUTS_DIR}/{INTERMEDIATE_FILE}", index=False)
    print(f"Saved temporal dataset to {INTERMEDIATE_FILE} with {len(df)} rows.")

def preprocess_data():
    df = pd.read_csv(f"{ML_OUTPUTS_DIR}/{INTERMEDIATE_FILE}")
   
    # Drop rows where optimal_cpu or optimal_ram is missing
    df = df.dropna(subset=["optimal_cpu", "optimal_ram"])

    features = [
        "cpu_usage",      
        "ram_usage",              
        "request_rate_actual",         
        "latency_p95",  
        "latency_p99",     
        "throttling",
        "average_response_time",
    ]

    targets = ["optimal_cpu", "optimal_ram"]  # What we want to predict

    df = df[features + targets]

    new_row = {feature: 0 for feature in features}
    new_row.update({"optimal_cpu": 200, "optimal_ram": 200})
    new_df = pd.DataFrame([new_row])
    df = pd.concat([df, new_df], ignore_index=True)

    nan_columns = df.columns[df.isna().any()].tolist()
    print("Columns with NaN values:", nan_columns)

    df = df.dropna()

    scaler = StandardScaler()
    X = df[features]
    y = df[targets]

    X_scaled = scaler.fit_transform(X)  # Normalized features
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42
    )

    # Save scaled features and targets
    np.savez(f"{ML_OUTPUTS_DIR}/preprocessed_data.npz", X_train=X_train, X_test=X_test, y_train=y_train, y_test=y_test)

    # Save the scaler for later use (e.g., in production)
    joblib.dump(scaler, f"{ML_OUTPUTS_DIR}/scaler.pkl")

def knn():
    # Load preprocessed data
    data = np.load(f"{ML_OUTPUTS_DIR}/preprocessed_data.npz")
    X_train, y_train = data["X_train"], data["y_train"]


    param_grid = {
        "n_neighbors": [3, 5, 7, 10],
        "weights": ["uniform", "distance"],
        "metric": ["euclidean", "manhattan"]
    }

    grid_search = GridSearchCV(
        KNeighborsClassifier(),
        param_grid,
        cv=5,               # 5-fold cross-validation
        scoring="neg_mean_squared_error",
        verbose=1
    )
    
    # Train the model
    grid_search.fit(X_train, y_train)

    # Best parameters
    print("Best hyperparameters:", grid_search.best_params_)

    # Retrain with best parameters
    best_knn = grid_search.best_estimator_
    best_knn.fit(X_train, y_train)

    # Save the model
    joblib.dump(best_knn, f"{ML_OUTPUTS_DIR}/knn_regressor.pkl")  # Save for later use

def evaluate_knn():
    # Load preprocessed data
    data = np.load(f"{ML_OUTPUTS_DIR}/preprocessed_data.npz")
    X_test, y_test = data["X_test"], data["y_test"]

    # Load knn model
    # Load the model
    model = joblib.load(f"{ML_OUTPUTS_DIR}/knn_regressor.pkl")

    # Transform test data with the same imputer
    imputer = SimpleImputer(strategy='constant', fill_value=0)
    X_test = imputer.fit_transform(X_test)
    X_test = imputer.transform(X_test)
    
    # Predict on test data
    y_pred = model.predict(X_test)

    # Calculate RMSE (Root Mean Squared Error)
    rmse_cpu = mean_squared_error(y_test[:, 0], y_pred[:, 0])
    rmse_ram = mean_squared_error(y_test[:, 1], y_pred[:, 1])

    print(f"RMSE for CPU: {rmse_cpu:.2f} millicores")
    print(f"RMSE for RAM: {rmse_ram:.2f} MiB")

    # R² Score (closer to 1 is better)
    r2_cpu = r2_score(y_test[:, 0], y_pred[:, 0])
    r2_ram = r2_score(y_test[:, 1], y_pred[:, 1])

    print(f"R² for CPU: {r2_cpu:.3f}")
    print(f"R² for RAM: {r2_ram:.3f}")

    mae_cpu = mean_absolute_error(y_test[:, 0], y_pred[:, 0])
    mae_ram = mean_absolute_error(y_test[:, 1], y_pred[:, 1])
    print(f"MAE (CPU): {mae_cpu:.2f} millicores")
    print(f"MAE (RAM): {mae_ram:.2f} MiB")

    relative_error_cpu = 100 * (y_pred[:, 0] - y_test[:, 0]) / y_test[:, 0]
    relative_error_ram = 100 * (y_pred[:, 1] - y_test[:, 1]) / y_test[:, 1]

    print(f"Mean Relative Error (CPU): {np.mean(np.abs(relative_error_cpu)):.2f}%")
    print(f"Mean Relative Error (RAM): {np.mean(np.abs(relative_error_ram)):.2f}%")

if __name__ == "__main__":
    if CREATE_INTERMEDIATE_DATASET:
        create_intermediate_dataset()
    if TRAIN:
        preprocess_data()
        knn()
    if EVALUATE:
        evaluate_knn()

