import pandas as pd
import numpy as np
import xgboost as xgb
import joblib
import math

from sklearn.model_selection import train_test_split, GridSearchCV, TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.multioutput import MultiOutputRegressor

# --- CONFIGURATION ---
# DATASET_PATH = "compiled_dataset_from_ahp_only.csv"
DATASET_PATH = "compiled_dataset_from_if_not_updated.csv"
MODEL_OUTPUT_DIR = "results"
SAFE_BUFFER_CPU = 1.10  # 15% Headroom for CPU
SAFE_BUFFER_RAM = 1.20  # 20% Headroom for RAM
THROTTLE_PENALTY = 1.20 # 50% penalty if throttling detected
FREEZE_PENALTY = 1.20   # 50% penalty to cpu if restarted
OOM_PENALTY = 2.0       # 100% penalty (Double RAM) if restart detected
LATENCY_SLA_MS = 700.0  # If P95 is above 500ms, we are in trouble
LATENCY_PENALTY = 1.10  # Request 30% more CPU if we are slow

def feature_engineering(df):
    """
    1. Sorts data.
    2. Calculates derivatives (velocity/trends).
    3. Handles missing values.
    """
    print("--- Feature Engineering ---")
    
    # Ensure time-based sorting for accurate diff() calculations
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'])
        df = df.sort_values(['flavor', 'Timestamp'])
    
    # Group by flavor so we don't diff across different pod types
    # (e.g. don't compare a 'small' pod's CPU to a 'medium' pod's CPU)
    grouped = df.groupby('flavor')

    # 1. Request Rate Trend (Acceleration)
    df['rps_trend'] = grouped['request_rate_raw'].diff(periods=12).fillna(0)
    
    # 2. CPU Trend (Velocity)
    df['cpu_trend'] = grouped['cpu_usage'].diff(periods=12).fillna(0)
    
    # 3. Latency Trend
    df['latency_trend'] = grouped['latency_p95'].diff(periods=12).fillna(0)

    # Fill any remaining NaNs (e.g., first rows of each group)
    df = df.fillna(0)
    
    print(f"Added trend features. Total rows: {len(df)}")
    return df

def generate_targets(df):
    """
    Calculates the 'Ground Truth' (Optimal CPU/RAM) based on penalties.
    """
    print("--- Generating Targets (Ground Truth) ---")

    def get_optimal_cpu(row):
        base_need = row['cpu_usage']
        
        # If throttling occurred, the reported usage is a lie (it's capped).
        # We need significantly more resources.
        if row['throttling'] > 0.1:
            base_need = base_need * THROTTLE_PENALTY
        if row['restarts'] > 0:
            base_need = base_need * THROTTLE_PENALTY
        if row['latency_p95'] > LATENCY_SLA_MS:
            # We assume higher CPU might help process the queue faster
            return base_need * LATENCY_PENALTY
        
        # Add standard safety buffer
        return base_need * SAFE_BUFFER_CPU

    def get_optimal_ram(row):
        base_need = row['ram_usage_raw']
        
        # If it restarted, assume OOM (Out of Memory) crash.
        # Drastically increase memory requirement.
        if row['restarts'] > 0:
            return base_need * OOM_PENALTY
        
        return base_need * SAFE_BUFFER_RAM

    df['optimal_cpu'] = df.apply(get_optimal_cpu, axis=1)
    df['optimal_ram'] = df.apply(get_optimal_ram, axis=1)
    
    return df

def train_model():
    # 1. Load Data
    df = pd.read_csv(DATASET_PATH)
    
    # Rename columns to match our logic if necessary
    # (Assuming the gathering script output matches these keys)
    if 'request_rate_raw' not in df.columns and 'request_rate' in df.columns:
        df.rename(columns={'request_rate': 'request_rate_raw'}, inplace=True)

    # 2. Apply Logic
    df = feature_engineering(df)
    df = generate_targets(df)

    # 3. Define Features and Targets
    # Note: 'flavor' is categorical and needs encoding
    categorical_features = ["flavor"]
    numeric_features = [
        "request_rate_raw", 
        "rps_trend", 
        # "cpu_usage", 
        "cpu_trend", 
        # "ram_usage_raw",
        "latency_p95",
        "latency_trend",
        "restarts" # Important context feature
    ]
    
    X = df[categorical_features + numeric_features]
    y = df[["optimal_cpu", "optimal_ram"]]

    # 4. Preprocessing Pipeline
    # We use ColumnTransformer to OneHotEncode 'flavor' automatically
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore'), categorical_features),
            ('num', 'passthrough', numeric_features)
        ]
    )

    # 5. Split Data
    # Shuffle=False is often better for time-series to prevent leakage, 
    # but since we have multiple flavors mixed, random split is okay 
    # IF the dataset covers enough time.
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # 6. Define the Model (XGBoost inside a MultiOutput wrapper)
    xgb_reg = xgb.XGBRegressor(objective='reg:squarederror', n_jobs=-1)
    
    # Wrap in MultiOutput because we predict CPU and RAM simultaneously
    multi_output_model = MultiOutputRegressor(xgb_reg)

    # Create full pipeline
    pipeline = Pipeline([
        ('preprocessor', preprocessor),
        ('regressor', multi_output_model)
    ])

    # 7. Grid Search Configuration
    print("--- Starting Grid Search (Hyperparameter Optimization) ---")
    param_grid = {
        # Access the estimator inside MultiOutputRegressor inside Pipeline
        'regressor__estimator__n_estimators': [100, 200, 300],
        'regressor__estimator__learning_rate': [0.05, 0.1],
        'regressor__estimator__max_depth': [3, 5, 7],
        'regressor__estimator__colsample_bytree': [0.8, 1.0]
    }

    grid_search = GridSearchCV(
        pipeline,
        param_grid,
        cv=3, # 3-Fold Cross Validation
        scoring='neg_mean_absolute_error',
        verbose=1,
        n_jobs=-1
    )

    grid_search.fit(X_train, y_train)

    print(f"Best Parameters: {grid_search.best_params_}")
    best_model = grid_search.best_estimator_

    # 8. Evaluate
    print("--- Evaluating Best Model ---")
    predictions = best_model.predict(X_test)
    
    # Calculate metrics
    mae_cpu = mean_absolute_error(y_test['optimal_cpu'], predictions[:, 0])
    mae_ram = mean_absolute_error(y_test['optimal_ram'], predictions[:, 1])
    r2_cpu = r2_score(y_test['optimal_cpu'], predictions[:, 0])
    r2_ram = r2_score(y_test['optimal_ram'], predictions[:, 1])

    print(f"MAE CPU: {mae_cpu:.2f} millicores")
    print(f"MAE RAM: {mae_ram:.2f} MiB")
    print(f"R² CPU: {r2_cpu:.4f}")
    print(f"R² RAM: {r2_ram:.4f}")

    # 9. Sanity Check / Example Prediction
    print("\n--- Example Predictions vs Actuals ---")
    example_indices = np.random.choice(len(X_test), 10, replace=False)
    
    # Get raw values for display
    X_test_display = X_test.iloc[example_indices].reset_index(drop=True)
    pred_display = predictions[example_indices]
    actual_display = y_test.iloc[example_indices].reset_index(drop=True)

    for i in range(10):
        flavor = X_test_display.loc[i, 'flavor']
        rps = X_test_display.loc[i, 'request_rate_raw']
        
        pred_cpu = pred_display[i][0]
        act_cpu = actual_display.loc[i, 'optimal_cpu']
        
        print(f"Flavor: {flavor:<7} | RPS: {rps:<4.0f} | Pred CPU: {pred_cpu:.0f}m | Actual Target: {act_cpu:.0f}m")

    # We extract the estimator for CPU to see what matters most
    multioutput_model = best_model.named_steps['regressor']
    xgb_cpu_model = multioutput_model.estimators_[0]
    preprocessor = best_model.named_steps['preprocessor']
    cat_names = preprocessor.named_transformers_['cat'].get_feature_names_out(categorical_features)
    all_feature_names = list(cat_names) + numeric_features
    importances = pd.DataFrame({
        'feature': all_feature_names,
        'importance': xgb_cpu_model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print("\nWhat drives CPU requirements?")
    print(importances)

    # 10. Save Model
    joblib.dump(best_model, f"{MODEL_OUTPUT_DIR}/vpa_xgboost_model.pkl")
    print(f"\nModel saved to {MODEL_OUTPUT_DIR}/vpa_xgboost_model.pkl")

if __name__ == "__main__":
    train_model()
