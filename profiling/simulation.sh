#!/bin/bash

# List of tags to test
TAGS=(
  "0.1.1-ahp-only"
  "0.1.1-if-not-updated"
  "0.1.1-independent"
  "0.1.1-knn-after"
  "0.1.1-three-to-one"
)

# Helm release name and namespace (Adjust these as needed)
RELEASE_NAME="ahp-autoscaler"
NAMESPACE="ahp"

for TAG in "${TAGS[@]}"; do
  echo "=================================================="
  echo "Starting test run for tag: $TAG"
  echo "=================================================="

  # 1. Update the Helm Release with the specific recommender tag
  echo "Updating Helm release..."
  helm upgrade $RELEASE_NAME /home/lefto/ahp-autoscaler/helm \
    --namespace $NAMESPACE \
    --set recommender.clientImageTag=$TAG \
    --set recommender.serverImageTag="0.1.1" \
    --set image.tag="0.3.0" \
    --wait

  # 2. Reset the Custom Resource (CR)
  echo "Resetting Custom Resource (ahpd.yaml)..."
  kubectl delete -f /home/lefto/ahp-autoscaler/examples/ahpdeployment.yaml --ignore-not-found=true
  
  # Optional: Wait briefly to ensure controller cleans up old resources
  sleep 5
  
  kubectl apply -f /home/lefto/ahp-autoscaler/examples/ahpdeployment.yaml

  sleep 5
  # 3. Create a unique output directory for this run to avoid overwriting
  # or ensure the python script handles unique naming based on an env var.
  # Here, I'm passing the TAG as an environment variable to the container.
  
  echo "Starting simulation container..."
  
  # Run the simulation synchronously (removed -d) so the script waits for it to finish.
  # If you need it detached, we have to add a wait logic.
  docker run \
    --name "simulation-$TAG" \
    --network host \
    -v ~/.kube/config:/root/.kube/config \
    -v "$(pwd)/outputs_simulation/0.3.0-$TAG-server-0.1.1:/app/outputs_simulation" \
    -v "$(pwd)/simulate.py:/app/simulate.py" \
    -v "/home/lefto/timestamps.txt:/app/timestamps.txt" \
    nexus.lefto.org/docker/load-test-runner:0.0.2 \
    python -u simulate.py

  echo "Simulation for $TAG completed."
  echo "--------------------------------------------------"
  
  # Optional: Sleep between runs to let the cluster settle
  sleep 10

done

echo "All tests completed."
