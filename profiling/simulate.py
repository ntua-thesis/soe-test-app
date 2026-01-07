import time
from datetime import datetime, timedelta
import os
import csv
import numpy as np
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

requests.packages.urllib3.disable_warnings()

# ================= CONFIGURATION =================

INPUT_TIMESTAMPS_FILE = 'timestamps.txt'
SIMULATION_DURATION_SECONDS = 5.2 * 60 * 60
INTERVAL = 1
RECOMMENDER_POD_NAME_LABEL = "ahp-soe-app-recommender"
REQUEST_TIMEOUT = 10     # Seconds
APP_URL = "http://30201.lefto.org/primes?n=600000"
PROMETHEUS_URL = "https://prometheus.lefto.org"
OUTPUT_DIR = "outputs_simulation"

# =================================================

def query_prometheus(metric_name, s):
    query = metric_name
    response = requests.get(
        f'{PROMETHEUS_URL}/api/v1/query_range', 
        params={
            'query': query,
            'end': datetime.now().timestamp(),
            'start': (datetime.now() - timedelta(seconds=s)).timestamp(),
            'step': '5s'
        }, 
        verify=False
    )
    data = response.json()
    return data['data']['result']

# Function to write metrics to a CSV file
def write_to_csv(metric_name, data):
    # Create the directory if it doesn't exist
    directory = Path("./metrics")
    directory.mkdir(parents=True, exist_ok=True)

    # Define the file path
    file_path = directory / f'{metric_name}.csv'

    # Write the data to the CSV file
    with open(file_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Timestamp', 'Value'])  # CSV header
        for result in data:
            for value in result['values']:
                timestamp = int(value[0] * 1000)
                metric_value = value[1]
                writer.writerow([timestamp, metric_value])

# Global counters for live reporting
stats = {
    "success": 0,
    "fail": 0,
    "total_success": 0,
    "total_fail": 0
}

def send_request():
    """Sends a single async request and updates stats."""
    try:
        response = requests.get(APP_URL, timeout=REQUEST_TIMEOUT, verify=False)
        if response.status_code == 200:
            stats["success"] += 1
            stats["total_success"] += 1
        else:
            stats["fail"] += 1
            stats["total_fail"] += 1
    except Exception:
        stats["fail"] += 1
        stats["total_fail"] += 1

def simulate_requests_from_timestamps(input_timestamps_file, simulation_duration_seconds, interval_seconds=1, max_workers=1000, pod_name="ahp-nginx-recommender-67d977b69d-zq595"):
    """
    Reads timestamps from a file and simulates sending requests based on
    the requests per second (RPS) calculated for each interval,
    using a ThreadPoolExecutor for concurrent requests.
    Also, counts successful and failed requests, queries Prometheus,
    writes metrics to CSV, and runs a kubectl command at the end.

    Args:
        input_timestamps_file (str): Path to the input file containing timestamps
                                   (milliseconds since epoch, one per line).
        simulation_duration_seconds (int): The predefined amount of time in hours for the simulation to run.
        interval_seconds (int): The time interval in seconds for grouping requests.
                                (e.g., 1 for per second, 60 for per minute).
        max_workers (int): The maximum number of threads to use for sending requests concurrently.
        pod_name (str): The name of the Kubernetes pod to get logs from at the end.
    """
    timestamps_ms = []
    print(f"Reading timestamps from '{input_timestamps_file}' for simulation...")

    try:
        with open(input_timestamps_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    ts_ms = int(line.strip())
                    timestamps_ms.append(ts_ms)
                except ValueError:
                    print(f"Warning: Skipping invalid timestamp on line {line_num}: '{line.strip()}'")
    except FileNotFoundError:
        print(f"Error: Input file '{input_timestamps_file}' not found.")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}")
        return

    if not timestamps_ms:
        print("No valid timestamps found in the file. Cannot simulate requests.")
        return

    # Sort timestamps to ensure correct chronological order
    timestamps_ms.sort()

    # Convert milliseconds timestamps to datetime objects
    timestamps_dt = [datetime.fromtimestamp(ts / 1000) for ts in timestamps_ms]

    # Determine the time range of the data
    min_time = timestamps_dt[0]
    max_time = timestamps_dt[-1]

    print(f"Simulation time range from input file: {min_time} to {max_time}")

    # Create time bins for the simulation
    start_bin = min_time.replace(microsecond=0)
    if start_bin > min_time:
        start_bin = start_bin - timedelta(seconds=1)

    bins = []
    current_bin = start_bin
    while current_bin <= max_time + timedelta(seconds=interval_seconds):
        bins.append(current_bin)
        current_bin += timedelta(seconds=interval_seconds)

    # Convert datetime objects to Unix timestamps (seconds) for numpy.histogram
    timestamps_unix = np.array([ts.timestamp() for ts in timestamps_dt])
    bin_edges_unix = np.array([b.timestamp() for b in bins])

    # Count requests in each interval
    counts, _ = np.histogram(timestamps_unix, bins=bin_edges_unix)

    total_requests_sent = 0
    start_simulation_time = time.time()
    end_simulation_deadline = start_simulation_time + simulation_duration_seconds

    print(f"\nStarting request simulation for {simulation_duration_seconds / 60 / 60} hours with {interval_seconds}-second intervals and {max_workers} concurrent workers...")
    print(f"Simulation will end at {datetime.fromtimestamp(end_simulation_deadline).strftime('%Y-%m-%d %H:%M:%S')}")
    print("-------------------------------------------------------------------")

    # Define Prometheus queries
    query_list = [
        {"name": "average_response_time", "query": 'avg(sum by (pod) (rate(istio_request_duration_milliseconds_sum{destination_service_name=~"ahp-soe-app-.*"} [10s])) / sum by (pod) (rate(istio_request_duration_milliseconds_count{destination_service_name=~"ahp-soe-app-.*"} [10s])))'},
        {"name": "latency_p99", "query": 'histogram_quantile(0.99, sum(rate(istio_request_duration_milliseconds_bucket{destination_service_name=~"ahp-soe-app-.*"}[30s])) by (le))'},
        {"name": "latency_p95", "query": 'histogram_quantile(0.95, sum(rate(istio_request_duration_milliseconds_bucket{destination_service_name=~"ahp-soe-app-.*"}[30s])) by (le))'},
        {"name": "request_rate_actual", "query": 'sum by (pod) (sum by (pod, status) ( sum(rate(istio_requests_total{destination_service_name=~"ahp-soe-app-.*"} [30s]))))'},
        {"name": "number_of_pods", "query": 'count(kube_pod_info{pod=~"ahp-soe-app-(small|medium|large).*"})'},
        {"name": "total_cpu", "query": 'sum(kube_pod_container_resource_limits{resource="cpu", pod=~"ahp-soe-app-(small|medium|large).*"})'},
        {"name": "cpu_per_limit", "query": 'sum(rate(container_cpu_usage_seconds_total{pod=~"ahp-soe-app-.*"}[1m])) / sum(kube_pod_container_resource_limits{resource="cpu", pod=~"ahp-soe-app-.*"}) * 100'},
        {"name": "throttling", "query": 'avg(rate(container_cpu_cfs_throttled_periods_total{pod=~"ahp-soe-app-.*"} [60s]))'},
        {"name": "total_memory", "query": 'sum(kube_pod_container_resource_limits{resource="memory", pod=~"ahp-soe-app-(small|medium|large).*"})'},
        {"name": "memory_per_limit", "query": 'sum(container_memory_working_set_bytes{pod=~"ahp-soe-app-.*"}) / sum(kube_pod_container_resource_limits{resource="memory", pod=~"ahp-soe-app-.*"}) * 100'},
        {"name": "restarts", "query": 'sum(rate(kube_pod_container_status_restarts_total{container="ahp-soe-app"}[5m]))'}
    ]


    # Use ThreadPoolExecutor for concurrent request sending
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Iterate through the calculated intervals and simulate requests
        i = 0
        while time.time() < end_simulation_deadline:
            if i >= len(counts):
                # If we've exhausted the timestamps, loop back to the beginning
                i = 0

            count = counts[i]
            current_interval_start_dt = bins[i]

            # Calculate the expected real-world time for this interval to start
            expected_elapsed_time = (current_interval_start_dt - start_bin).total_seconds()
            actual_elapsed_time = time.time() - start_simulation_time

            # If the simulation is running too fast, pause to catch up
            if actual_elapsed_time < expected_elapsed_time and time.time() < end_simulation_deadline:
                sleep_time = expected_elapsed_time - actual_elapsed_time
                time.sleep(min(sleep_time, end_simulation_deadline - time.time())) # Don't sleep past the deadline

            if time.time() >= end_simulation_deadline:
                break

            futures = []
            for _ in range(count):
                if time.time() >= end_simulation_deadline:
                    break
                futures.append(executor.submit(send_request))
                total_requests_sent += 1

            # Optionally, wait for all requests in the current interval to complete
            # This can be useful if you need to ensure all requests for a given second
            # are done before moving to the next second.
            # for future in as_completed(futures):
            #     try:
            #         result = future.result()
            #         if result:
            #             successful_requests += 1
            #         else:
            #             failed_requests += 1
            #     except Exception as exc:
            #         print(f'Request generated an exception: {exc}')
            #         failed_requests += 1
            i += 1

    end_simulation_time = time.time()
    duration = end_simulation_time - start_simulation_time

    m1 = f"Simulation complete after {duration:.2f} seconds."
    m2 = f"Total requests sent: {total_requests_sent}"
    m3 = f"Successful requests: {stats['total_success']}"
    m4 = f"Failed requests: {stats['total_fail']}"
    m5 = f"Average simulated RPS: {total_requests_sent / duration:.2f}"

    print("-------------------------------------------------------------------")
    print(m1); print(m2); print(m3); print(m4)
    if duration > 0:
        print(m5)

    # Ensure the directory exists
    output_dir = OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    output_filepath = os.path.join(output_dir, "results.txt")

    with open(output_filepath, 'w') as f:
        f.write(f"{m1}\n"); f.write(f"{m2}\n"); f.write(f"{m3}\n"); f.write(f"{m4}\n");
        if duration > 0:
            f.write(f"{m5}\n") 

    print(f"Simulation results written to {output_filepath}")

    print("\nQuerying Prometheus and exporting metrics...")
    for query_info in query_list:
        metric_name = query_info["name"]
        query = query_info["query"]
        print(f"  Executing query: {metric_name}")
        data = query_prometheus(query, simulation_duration_seconds)
        if data:
            write_to_csv(metric_name, data)
            print(f"  Metrics for '{metric_name}' written to CSV.")
        else:
            print(f"  No data returned for '{metric_name}'.")

    print(f"\nRunning kubectl logs command for pod: {pod_name}")
    log_command = f"kubectl logs -l name={pod_name} -n ahp-app --tail=-1 > outputs_simulation/recommender.log"
    try:
        os.system(log_command)
        print(f"Logs saved to recommender.log")
    except Exception as e:
        print(f"Error running kubectl command: {e}")

    try:
        os.system("cp -r metrics outputs_simulation")
        print(f"Copied metrics to outputs_simulation/metrics")
    except Exception as e:
        print(f"Error running cp command")


# --- Run the script ---
if __name__ == "__main__":
    # The dummy file creation logic has been removed.
    # Ensure 'timestamps.txt' exists in the same directory or provide its full path.
    simulate_requests_from_timestamps(INPUT_TIMESTAMPS_FILE, SIMULATION_DURATION_SECONDS, INTERVAL, pod_name=RECOMMENDER_POD_NAME_LABEL)