import pandas as pd
from prometheus_api_client import PrometheusConnect
from datetime import datetime
import urllib3

# Suppress warnings about unverified HTTPS requests (since we are disabling SSL verify)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
PROMETHEUS_URL = "https://prometheus.lefto.org"
# OUTPUT_FILE = "compiled_dataset_from_if_not_updated.csv"
OUTPUT_FILE = "compiled_dataset_from_ahp_only.csv"

# Precise Time Window (Based on your URL parameters)
# End time: 2026-01-10 04:31:25
# Range: 5h 15m -> Start time is roughly 23:16 on the previous day
# END_TIME = datetime(2026, 1, 10, 4, 31, 25) # if not updated time
END_TIME = datetime(2026, 1, 9, 23, 19, 25) # ahp only
START_TIME = END_TIME - pd.Timedelta(hours=5, minutes=15)

STEP = "5s"  # High resolution
POD_REGEX = "ahp-soe-app-.*"

def fetch_metric(prom, query, start_time, end_time, metric_name):
    """
    Helper to fetch a metric and convert to a clean DataFrame.
    """
    print(f"Fetching {metric_name}...")
    
    # Get data from Prometheus
    # verify=False is crucial for self-signed certs
    try:
        metric_data = prom.custom_query_range(
            query=query,
            start_time=start_time,
            end_time=end_time,
            step=STEP
        )
    except Exception as e:
        print(f"Error fetching {metric_name}: {e}")
        return pd.DataFrame()

    records = []
    for result in metric_data:
        # Extract name to identify flavor
        raw_name = result['metric'].get('pod') or \
                   result['metric'].get('destination_workload') or \
                   result['metric'].get('workload') or \
                   result['metric'].get('destination_service_name') or \
                   result['metric'].get('created_by_name')
        
        if not raw_name:
            continue

        # Flavor Extraction Logic
        flavor = "unknown"
        if "small" in raw_name: flavor = "small"
        elif "medium" in raw_name: flavor = "medium"
        elif "large" in raw_name: flavor = "large"
        
        # Parse values
        for value in result['values']:
            timestamp = datetime.fromtimestamp(float(value[0]))
            val = float(value[1])
            records.append({
                'Timestamp': timestamp,
                'flavor': flavor,
                metric_name: val
            })

    # print(query)
    # print(pd.DataFrame(records)) 
    return pd.DataFrame(records)

def main():
    # Connect with disable_ssl=True (which sets verify=False internally)
    prom = PrometheusConnect(url=PROMETHEUS_URL, disable_ssl=True)
    
    # Verify connection
    if prom.check_prometheus_connection():
        print("Connected to Prometheus successfully.")
    else:
        print("Failed to connect to Prometheus.")
        return

    print(f"Time Window: {START_TIME} to {END_TIME}")
    print(f"Resolution: {STEP}")

    # --- DEFINE QUERIES ---
    
    # 1. CPU Usage (Millicores)
    # Using 30s rate to smooth out the 5s resolution slightly, or use [5s] if you want raw volatility
    query_cpu = f'sum(rate(container_cpu_usage_seconds_total{{pod=~"{POD_REGEX}"}}[30s])) by (pod)'

    # 2. Memory Usage (MiB)
    query_ram = f'sum(container_memory_working_set_bytes{{pod=~"{POD_REGEX}"}}) by (pod) / 1024 / 1024'

    # 3. Request Rate (RPS)
    # Note: Your URL used destination_service_name, so we align with that
    query_rps_total  = f'sum(rate(istio_requests_total{{destination_service_name=~"{POD_REGEX}"}}[30s])) by (destination_service_name)'
    query_replicas = f'count(kube_pod_info{{pod=~"{POD_REGEX}"}}) by (created_by_name)' 

    # 4. Latency P95 (ms)
    query_latency = f'histogram_quantile(0.95, sum(rate(istio_request_duration_milliseconds_bucket{{destination_service_name=~"{POD_REGEX}"}}[30s])) by (le, destination_service_name))'
    
    # 5. CPU Throttling (Seconds)
    query_throttle = f'sum(rate(container_cpu_cfs_throttled_periods_total{{pod=~"{POD_REGEX}"}}[30s])) by (pod)'

    # 6. Restarts (Count)
    # 'changes' counts how many times the restart counter increased in the window
    query_restarts = f'sum(changes(kube_pod_container_status_restarts_total{{pod=~"{POD_REGEX}"}}[1m])) by (pod)'

    # --- FETCH DATA ---
    df_cpu = fetch_metric(prom, query_cpu, START_TIME, END_TIME, "cpu_usage_raw")
    df_ram = fetch_metric(prom, query_ram, START_TIME, END_TIME, "ram_usage_raw")
    df_rps_total  = fetch_metric(prom, query_rps_total, START_TIME, END_TIME, "rps_total")
    df_replicas = fetch_metric(prom, query_replicas, START_TIME, END_TIME, "replica_count")
    df_lat = fetch_metric(prom, query_latency, START_TIME, END_TIME, "latency_p95")
    df_thr = fetch_metric(prom, query_throttle, START_TIME, END_TIME, "throttling")
    df_restarts = fetch_metric(prom, query_restarts, START_TIME, END_TIME, "restarts")

    # --- MERGE DATA ---
    print("Merging datasets...")

    # Merge RPS and Replicas first
    if not df_rps_total.empty and not df_replicas.empty:
        # Round timestamps to align
        df_rps_total['Timestamp'] = df_rps_total['Timestamp'].dt.round('5s')
        df_replicas['Timestamp'] = df_replicas['Timestamp'].dt.round('5s')
        
        # Merge on Timestamp and Flavor
        df_rps_calc = pd.merge(df_rps_total, df_replicas, on=['Timestamp', 'flavor'], how='inner')
        
        # Calculate Per-Pod RPS
        # Avoid division by zero
        df_rps_calc['request_rate_raw'] = df_rps_calc['rps_total'] / df_rps_calc['replica_count'].replace(0, 1)
        
        # Keep only the columns we need
        df_rps = df_rps_calc[['Timestamp', 'flavor', 'request_rate_raw']].copy()
    else:
        print("Warning: Could not calculate per-pod RPS (missing traffic or replica data)")
        df_rps = pd.DataFrame()

    df_cpu['Timestamp'] = df_cpu['Timestamp'].dt.round('5s')
    
    if not df_ram.empty:
        df_ram['Timestamp'] = df_ram['Timestamp'].dt.round('5s')
        
    if not df_rps.empty:
        df_rps['Timestamp'] = df_rps['Timestamp'].dt.round('5s')
        
    if not df_lat.empty:
        df_lat['Timestamp'] = df_lat['Timestamp'].dt.round('5s')
        
    if not df_thr.empty:
        df_thr['Timestamp'] = df_thr['Timestamp'].dt.round('5s')

    def clean_group(df):
        if df.empty: return df
        return df.groupby(['Timestamp', 'flavor']).mean().reset_index()
    
    df_cpu = clean_group(df_cpu)
    df_ram = clean_group(df_ram)
    df_rps = clean_group(df_rps)
    df_lat = clean_group(df_lat)
    df_thr = clean_group(df_thr)

    # Start merging
    final_df = df_cpu
    if final_df.empty:
        print("Error: No CPU data found. Check your regex or time window.")
        return

    if not df_ram.empty: final_df = pd.merge(final_df, df_ram, on=['Timestamp', 'flavor'], how='inner')
    if not df_rps.empty: final_df = pd.merge(final_df, df_rps, on=['Timestamp', 'flavor'], how='inner')
    if not df_lat.empty: final_df = pd.merge(final_df, df_lat, on=['Timestamp', 'flavor'], how='left')
    if not df_thr.empty: final_df = pd.merge(final_df, df_thr, on=['Timestamp', 'flavor'], how='left')
    if not df_thr.empty: final_df = pd.merge(final_df, df_restarts, on=['Timestamp', 'flavor'], how='left')

    # Fill NaNs
    final_df['throttling'] = final_df['throttling'].fillna(0)
    final_df['latency_p95'] = final_df['latency_p95'].fillna(0)
    final_df['restarts'] = final_df['restarts'].fillna(0)

    # --- POST-PROCESSING ---
    # Convert CPU to millicores
    final_df['cpu_usage'] = final_df['cpu_usage_raw'] * 1000
    final_df.drop(columns=['cpu_usage_raw'], inplace=True)

    # Save
    final_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Success! Saved {len(final_df)} rows to {OUTPUT_FILE}")
    print(final_df.head())

if __name__ == "__main__":
    main()
