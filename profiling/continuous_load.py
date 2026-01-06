import asyncio
import aiohttp
import time
import sys
import subprocess
import numpy as np

# ================= CONFIGURATION =================
# 1. Kubernetes / Helm Details
HELM_RELEASE_NAME = "soe-test-app" 
HELM_CHART_PATH = "/chart"  # Or "/chart" if running in Docker with volume
NAMESPACE = "test"

# 2. Target Resource Limits (Change these to what you want to test)
TARGET_CPU = "600m"
TARGET_MEMORY = "768Mi"

# 3. Load Settings
APP_URL = "http://30200.lefto.org/primes?n=600000"
TARGET_RPS = 25          # Requests per second
REQUEST_TIMEOUT = 10     # Seconds
IMAGE_TAG= "0.0.1-64bit"
# =================================================

# Global counters for live reporting
stats = {
    "success": 0,
    "fail": 0,
    "total_success": 0,
    "total_fail": 0
}

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
        "--set", f"image.tag={IMAGE_TAG}",
        "--wait" # Wait for pods to be ready
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        print("✅ Deployment updated and ready.")
        print("⏳ Waiting 5s for ingress/network stabilization...")
        time.sleep(5)
    except subprocess.CalledProcessError as e:
        print(f"❌ Helm update failed: {e}")
        sys.exit(1)

async def send_request(session, url):
    """Sends a single async request and updates stats."""
    try:
        async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
            await response.read()
            if response.status == 200:
                stats["success"] += 1
                stats["total_success"] += 1
            else:
                stats["fail"] += 1
                stats["total_fail"] += 1
    except Exception:
        stats["fail"] += 1
        stats["total_fail"] += 1

async def reporter():
    """Prints live stats every second."""
    start_time = time.time()
    while True:
        await asyncio.sleep(1)
        
        # Calculate current rates
        s = stats["success"]
        f = stats["fail"]
        total = s + f
        
        # Reset interval counters
        stats["success"] = 0
        stats["fail"] = 0
        
        elapsed = time.time() - start_time
        
        # Clear line and print status
        sys.stdout.write(f"\r[⏱️ {int(elapsed)}s] Current: {total} RPS ({s} OK, {f} ERR) | Total: {stats['total_success']} OK, {stats['total_fail']} ERR")
        sys.stdout.flush()

async def load_generator():
    """Generates Poisson load."""
    print(f"🚀 Starting Continuous Load: Target {TARGET_RPS} RPS")
    print(f"🎯 Target URL: {APP_URL}")
    print("Press Ctrl+C to stop...\n")

    async with aiohttp.ClientSession() as session:
        scale = 1.0 / TARGET_RPS
        
        while True:
            # Fire request
            asyncio.create_task(send_request(session, APP_URL))
            
            # Sleep based on Poisson distribution
            delay = np.random.exponential(scale=scale)
            await asyncio.sleep(delay)

async def main():
    # 1. Run Helm Update First
    run_helm_update(TARGET_CPU, TARGET_MEMORY)

    # 2. Run reporter and generator concurrently
    await asyncio.gather(
        reporter(),
        load_generator()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Load test stopped.")
        print(f"Final Totals: {stats['total_success']} Success, {stats['total_fail']} Failed")
