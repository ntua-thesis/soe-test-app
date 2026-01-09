import pandas as pd
import os
import glob
import re

# ================= CONFIGURATION =================
RESULTS_DIR = "/app/results"  # The folder containing <cpu>_<mem> subfolders
MODEL_OUTPUT = "knn_scaler_model.pkl"
DATASET_OUTPUT = "compiled_dataset.csv" # We will save the compiled CSV for records

CREATE_DATASET = True

# Cost Weighting (Adjust as needed)
def calculate_cost(cpu_str, mem_str):
    # Parse CPU (remove 'm')
    try:
        cpu_val = int(cpu_str.replace('m', ''))
    except:
        cpu_val = 0 # Handle edge cases
    
    # Parse Memory (remove 'Mi', handle 'Gi')
    if 'Gi' in mem_str:
        mem_val = int(mem_str.replace('Gi', ''))
    else:
        mem_val = int(mem_str.replace('Mi', '')) / 1024
        
    return ((cpu_val * 0.024) + (mem_val * 0.003)) * 720
# =================================================

def parse_summary_file(filepath):
    """Parses summary.txt to extract success/fail counts."""
    stats = {}
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            # Regex to find numbers
            # "Successful requests: 475"
            s_match = re.search(r"Successful requests:\s*(\d+)", content)
            f_match = re.search(r"Failed requests:\s*(\d+)", content)
            
            if s_match: stats['success_count'] = int(s_match.group(1))
            if f_match: stats['fail_count'] = int(f_match.group(1))
            
            # Calculate rates
            total = stats.get('success_count', 0) + stats.get('fail_count', 0)
            stats['total_reqs'] = total
            stats['success_rate'] = stats['success_count'] / total if total > 0 else 0.0
            
    except Exception as e:
        print(f"⚠️ Error parsing {filepath}: {e}")
    return stats

def load_data_from_directories(base_dir):
    """Crawls the results directory and builds a DataFrame."""
    all_runs_data = [] # Rename to be clear this holds full runs, not fragments

    if not os.path.exists(base_dir):
        print(f"❌ Directory {base_dir} does not exist.")
        return pd.DataFrame()

    config_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    print(f"📂 Found {len(config_dirs)} configuration folders.")

    for config in config_dirs:
        try:
            cpu_conf, mem_conf = config.split('_')
        except ValueError:
            continue
            
        config_path = os.path.join(base_dir, config)
        rps_dirs = [d for d in os.listdir(config_path) if os.path.isdir(os.path.join(config_path, d))]

        for rps_dir in rps_dirs:
            try:
                rps_val = int(rps_dir.replace('rps', ''))
            except ValueError:
                continue

            current_rps_path = os.path.join(config_path, rps_dir)
            summary_path = os.path.join(current_rps_path, "summary.txt")
            
            if not os.path.exists(summary_path):
                continue

            stats = parse_summary_file(summary_path) # Assuming this function exists

            # --- CHANGE STARTS HERE ---
            
            # We will collect all metrics for THIS specific run here
            dfs_for_this_run = []
            
            csv_files = glob.glob(os.path.join(current_rps_path, "*.csv"))
            
            for csv_file in csv_files:
                metric_name = os.path.basename(csv_file).replace(".csv", "")
                try:
                    df = pd.read_csv(csv_file)
                except Exception as e:
                    print(f"Error reading {csv_file}: {e}")
                    continue

                # Standardize Timestamp
                df['Timestamp'] = (df['Timestamp'] / 2).round().astype(int)
                
                # 1. Group by Timestamp immediately to handle duplicate seconds in raw data
                # 2. Rename 'Value' to the specific metric name
                df_metric = df.groupby('Timestamp')['Value'].mean().rename(metric_name)
                
                dfs_for_this_run.append(df_metric)

            if not dfs_for_this_run:
                continue

            # Merge all metrics for this run horizontally (axis=1) based on Timestamp index
            # This creates a dense DataFrame: [Timestamp, cpu_usage, memory_usage, latency, etc.]
            run_df = pd.concat(dfs_for_this_run, axis=1)
            
            run_df['average_run_cpu'] = run_df['cpu_per_limit_for_60s'].mean()
            run_df['cpu'] = cpu_conf.replace("m", "")
            run_df['memory'] = int(mem_conf.replace("Gi", "").replace("Mi", "")) * (1024 if "Gi" in mem_conf else 1)
            run_df['target_rps'] = rps_val
            run_df['success_rate'] = stats["success_rate"]
            
            # Reset index so Timestamp becomes a column again
            run_df = run_df.reset_index()

            all_runs_data.append(run_df)

    # Final concatenation is now much lighter
    if not all_runs_data:
        return pd.DataFrame()

    combined_df = pd.concat(all_runs_data, ignore_index=True)
    
    # Optional: Fill NaNs if timestamps didn't perfectly align between CSVs
    # combined_df = combined_df.fillna(0) 

    return combined_df

def main():
    if CREATE_DATASET:
        print("--- 1. Crawling Directories & Building Dataset ---")
        df = load_data_from_directories(RESULTS_DIR)
        
        if df.empty:
            print("❌ No data found. Check your directory structure.")
            return

        # Save the raw compiled data for inspection
        df.to_csv(DATASET_OUTPUT, index=False)
        print(f"   ✅ Data compiled into {DATASET_OUTPUT} ({len(df)} rows)")

if __name__ == "__main__":
    main()
