import asyncio
import aiohttp
import time
import subprocess
import requests
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# ================= CONFIGURATION =================
# Kubernetes / Helm Details
HELM_RELEASE_NAME = "soe-test-app" 
HELM_CHART_PATH = "/chart" 
NAMESPACE = "test"
APP_URL = "http://30200.lefto.org/primes?n=1000000"
PROMETHEUS_URL = "https://prometheus.lefto.org"
RESULTS_DIR = "./results"

# Experiment Settings
DURATION_PER_STEP = 10  # 5 minutes in seconds
REQUEST_TIMEOUT = 10     # Seconds
SUCCESS_THRESHOLD = 0.95 # Stop if success rate < 95%

# Resource Configurations
RESOURCE_CONFIGS = [
    {"cpu": "200m", "memory": "128Mi", "min_rps": 1, "max_rps": 10, "step_rps": 1},
    {"cpu": "500m", "memory": "256Mi", "min_rps": 5, "max_rps": 20, "step_rps": 2},
    {"cpu": "1000m", "memory": "512Mi", "min_rps": 10, "max_rps": 40, "step_rps": 5}
]

# Prometheus Queries to Export (Key = Filename, Value = PromQL)
# Note: $POD_REGEX will be replaced by the script
PROMETHEUS_QUERIES = {
    "request_rate_for_30s": 'sum by (pod) (sum by (pod, status) ( sum(rate(istio_requests_total{destination_canonical_service="chart"} [30s]))))',
    "cpu_per_limit_for_60s": 'sum(rate(container_cpu_usage_seconds_total{pod=~"soe-test-app-chart-.*"}[1m])) / sum(kube_pod_container_resource_limits{resource="cpu", container="chart"}) * 100',
    "art_for_10s": 'avg(sum by (pod) (rate(istio_request_duration_milliseconds_sum{destination_canonical_service="chart"} [10s])) / sum by (pod) (rate(istio_request_duration_milliseconds_count{destination_canonical_service="chart"} [10s])))',
    "cpu_throttling_60s": 'avg(rate(container_cpu_cfs_throttled_periods_total{pod=~"soe-test-app.*"} [60s]))',
    "memory_per_limit": 'sum(container_memory_working_set_bytes{pod=~"soe-test-app-.*"}) / sum(kube_pod_container_resource_limits{resource="memory", container="chart"}) * 100',
    "latency_p99": 'histogram_quantile(0.99, sum(rate(istio_request_duration_milliseconds_bucket{destination_canonical_service="chart"}[30s])) by (le))',
    "latency_p95": 'histogram_quantile(0.95, sum(rate(istio_request_duration_milliseconds_bucket{destination_canonical_service="chart"}[30s])) by (le))'
}
# =================================================

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def run_helm_update(cpu, memory):
    """Updates the deployment resource limits via Helm."""
    print(f"--- 🛠 Updating Helm: CPU={cpu}, Mem={memory} ---")
    cmd = [
        "helm", "upgrade", HELM_RELEASE_NAME, HELM_CHART_PATH,
        "--namespace", NAMESPACE,
        "--set", f"resources.limits.cpu={cpu}",
        "--set", f"resources.limits.memory={memory}",
        "--set", f"resources.requests.cpu={cpu}",
        "--set", f"resources.requests.memory={memory}",
        "--wait"
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        print("✅ Deployment updated and ready.")
        # Give it a small buffer to stabilize
        time.sleep(10)
    except subprocess.CalledProcessError as e:
        print(f"❌ Helm update failed: {e}")
        sys.exit(1)

async def send_request(session, url):
    try:
        async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
            await response.read()
            return "success" if response.status == 200 else "fail"
    except Exception:
        return "fail"

async def run_load_test(rps, duration):
    """Generates Poisson load."""
    print(f"🚀 Starting Load Test: Target {rps} RPS for {duration}s...")
    
    tasks = []
    stats = {"success": 0, "fail": 0}

    async def fire_and_track(session, url):
        status = await send_request(session, url)
        if status == "success":
            stats["success"] += 1
        else:
            stats["fail"] += 1

    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        end_time = start_time + duration
        scale = 1.0 / rps

        while time.time() < end_time:
            task = asyncio.create_task(fire_and_track(session, APP_URL))
            tasks.append(task)
            delay = np.random.exponential(scale=scale)
            await asyncio.sleep(delay)

        if tasks:
            pending = [t for t in tasks if not t.done()]
            if pending:
                await asyncio.wait(pending, timeout=REQUEST_TIMEOUT + 2)

    actual_duration = time.time() - start_time
    return stats["success"], stats["fail"], actual_duration, start_time

def export_prometheus_data(output_dir, start_ts, end_ts):
    """Queries Prometheus for a range of data and saves CSVs."""
    pod_regex = f"{HELM_RELEASE_NAME}.*"
    
    # Add a small buffer to start/end times to capture edge data
    start_str = datetime.fromtimestamp(start_ts).isoformat() + "Z"
    end_str = datetime.fromtimestamp(end_ts).isoformat() + "Z"
    
    step = "5s" # Resolution of data points

    for name, query in PROMETHEUS_QUERIES.items():
        final_query = query.replace("$POD_REGEX", pod_regex)
        
        params = {
            'query': final_query,
            'start': start_str,
            'end': end_str,
            'step': step
        }
        
        try:
            response = requests.get(f"{PROMETHEUS_URL}/api/v1/query_range", params=params, verify=False)
            data = response.json()
            
            if data['status'] == 'success' and len(data['data']['result']) > 0:
                # We assume the query returns a single time series (sum/avg). 
                # If it returns multiple, we take the first one or you'd need to loop them.
                values = data['data']['result'][0]['values']
                
                # Convert to DataFrame
                df = pd.DataFrame(values, columns=['Timestamp', 'Value'])
                # Prometheus returns timestamps in seconds, ensure they are clean
                # Save to CSV
                csv_path = os.path.join(output_dir, f"{name}.csv")
                df.to_csv(csv_path, index=False)
                print(f"   📄 Saved {name}.csv")
            else:
                print(f"   ⚠️ No data for {name}")
                
        except Exception as e:
            print(f"   ❌ Query failed for {name}: {e}")

async def main():
    ensure_dir(RESULTS_DIR)

    for config in RESOURCE_CONFIGS:
        cpu_conf = config["cpu"]
        mem_conf = config["memory"]
        
        # Create Config Directory (e.g., results/200m_128Mi)
        config_dir_name = f"{cpu_conf}_{mem_conf}"
        config_path = os.path.join(RESULTS_DIR, config_dir_name)
        ensure_dir(config_path)

        run_helm_update(cpu_conf, mem_conf)
        
        current_rps = config["min_rps"]
        while current_rps <= config["max_rps"]:
            
            # Create RPS Directory (e.g., results/200m_128Mi/10rps)
            rps_path = os.path.join(config_path, f"{current_rps}rps")
            ensure_dir(rps_path)

            # --- RUN TEST ---
            success, fail, duration, start_ts = await run_load_test(current_rps, DURATION_PER_STEP)
            end_ts = time.time()

            # --- WRITE SUMMARY.TXT ---
            summary_path = os.path.join(rps_path, "summary.txt")
            with open(summary_path, "w") as f:
                f.write(f"Starting stress test for {DURATION_PER_STEP} seconds, rate {current_rps} per second...\n")
                f.write(f"Stress test completed in {duration:.2f} seconds.\n")
                f.write(f"Successful requests: {success}\n")
                f.write(f"Failed requests: {fail}\n")
            print(f"   📝 Saved summary.txt")

            # --- EXPORT PROMETHEUS CSVs ---
            print("   ⏳ Waiting for metrics ingestion...")
            time.sleep(15) # Wait for Prometheus to scrape the last bits
            export_prometheus_data(rps_path, start_ts, end_ts)

            # --- CHECK THRESHOLD ---
            total = success + fail
            rate = success / total if total > 0 else 0
            if rate < SUCCESS_THRESHOLD:
                print(f"🛑 Success rate {rate:.2f} < {SUCCESS_THRESHOLD}. Stopping config.")
                break 

            current_rps += config["step_rps"]

if __name__ == "__main__":
    # Disable warnings for unverified HTTPS requests
    requests.packages.urllib3.disable_warnings()
    asyncio.run(main())
