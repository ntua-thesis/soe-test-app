import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# OG thresholds
# (group["average_response_time"] < 400) &
# (group["latency_p99"] < 1000) &
# (group["latency_p95"] < 800) &
# (group["success_rate"] >= 0.97) &
# (group["throttling"] < 0.4) &       # No throttling 0.1
# (group["ram_usage"] <= 90)          # No OOM risk

# 1. Load Data
try:
    df = pd.read_csv('compiled_dataset.csv')
except FileNotFoundError:
    print("Error: 'compiled_dataset.csv' not found.")
    exit()

# ---------------------------------------------------------
# 2. Preprocessing: Define what "Optimal" means
# ---------------------------------------------------------

# Filter dataset to only include successful runs
good_runs = df[
    (df['latency_p99'] <= 1000) &
    (df['latency_p95'] <= 800) &
    (df['art_for_10s'] <= 500) &
    (df['success_rate'] >= 0.99)
].copy()

if good_runs.empty:
    print("Error: No data points met the SLA criteria. Relax the thresholds.")
    exit()

print(f"{len(good_runs)} raw points met the SLA criteria.")

# ---------------------------------------------------------
# 3. The Critical Fix: Select the "Cheapest" Config per RPS
# ---------------------------------------------------------

# Define a simple cost function (e.g., 1 CPU unit = 1 Cost, 1 MB Ram = 0.5 Cost)
# Adjust these weights based on what is more expensive in your cloud provider
good_runs['cost_score'] = ((good_runs['cpu'] *  0.024) + (good_runs['memory'] * 0.003 / 1024)) * 720

# Sort by RPS (ascending) and then Cost (ascending)
good_runs = good_runs.sort_values(by=['target_rps', 'cost_score'], ascending=[True, True])

# Group by RPS and take the FIRST record (which is the cheapest due to sort)
# This removes the ambiguity. Now 50 RPS maps to ONLY ONE optimal config.
optimal_data = good_runs.groupby('target_rps').first().reset_index()

print(f"{len(optimal_data)} unique optimal configurations identified (one per RPS level).")

# Create labels
optimal_data['config_label'] = (
    optimal_data['cpu'].astype(str) + "CPU_" + 
    optimal_data['memory'].astype(str) + "MB"
)

# ---------------------------------------------------------
# 4. Train Model
# ---------------------------------------------------------

X = optimal_data[['target_rps']]
y = optimal_data['config_label']

# Since we reduced the dataset significantly (1 row per RPS), 
# we might not have enough data for a robust train/test split if RPS values are sparse.
# However, for the sake of the example, we proceed.
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

clf = RandomForestClassifier(n_estimators=100, random_state=42)
clf.fit(X_train, y_train)

# Evaluate
y_pred = clf.predict(X_test)
print(f"Model Accuracy: {accuracy_score(y_test, y_pred):.2f}")

# ---------------------------------------------------------
# 5. Test Recommender
# ---------------------------------------------------------
print("-" * 30)
print("Dynamic Configuration Recommender")
print("-" * 30)

# Since you mentioned your RPS is 0-50, let's test relevant values
test_loads = list(range(0, 51))

def recommend_config(current_rps):
    input_data = pd.DataFrame({'target_rps': [current_rps]})
    predicted_config = clf.predict(input_data)[0]
    probs = clf.predict_proba(input_data)
    confidence = np.max(probs)
    return predicted_config, confidence

for load in test_loads:
    config, conf = recommend_config(load)
    print(f"Incoming Load: {load} RPS -> Recommended Config: {config} (Confidence: {conf:.2f})")
