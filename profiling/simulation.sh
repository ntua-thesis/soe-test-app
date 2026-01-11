#!/bin/bash

# Before running checkout both ahp-autoscaler repo and this one

TAGS_CONFIG=(
  # ["0.1.1-ahp-only"]="ahpdeployment.yaml"
  # ["0.2.1-if-not-updated"]="ahpdeployment.yaml"
  # ["0.1.1-independent"]="ahpdeployment-independent.yaml"
  # ["0.2.0-knn-after"]="ahpdeployment-knn.yaml"
  "0.2.1-three-to-one:ahpdeployment_one_max.yaml"
  "0.2.1-if-not-updated:ahpdeployment.yaml"
  "0.2.1-three-to-one:ahpdeployment.yaml"
  "0.2.1-if-not-updated:ahpdeployment_one_max.yaml"
)

SERVER_TAG="0.2.0"
OPERATOR_TAG="0.3.0"

# Helm release name and namespace (Adjust these as needed)
RELEASE_NAME="ahp-autoscaler"
NAMESPACE="ahp"
EXAMPLES_PATH="/home/lefto/ahp-autoscaler/examples"

# Iterate over the keys (the tags)
for CONFIG in "${TAG_CONFIGS[@]}"; do
  TAG="${CONFIG%%:*}"      # Everything before the colon
  CR_FILENAME="${CONFIG#*:}" # Everything after the colon
  
  echo "=================================================="
  echo "Starting test run for tag: $TAG"
  echo "Using Custom Resource file: $CR_FILENAME"
  echo "=================================================="

  SIMULATION_DESCRIPTION="$OPERATOR_TAG-$TAG-server-$SERVER_TAG"

  # 1. Update the Helm Release with the specific recommender tag
  echo "Updating Helm release..."
  helm upgrade $RELEASE_NAME /home/lefto/ahp-autoscaler/helm \
    --namespace $NAMESPACE \
    --set recommender.clientImageTag="$TAG" \
    --set recommender.serverImageTag="$SERVER_TAG" \
    --set image.tag="$OPERATOR_TAG" \
    --wait

  # 2. Reset the Custom Resource (CR)
  echo "Resetting Custom Resource ($CR_FILENAME)..."
  kubectl delete -f "$EXAMPLES_PATH/$CR_FILENAME" --ignore-not-found=true
  
  # Optional: Wait briefly to ensure controller cleans up old resources
  sleep 5
  
  kubectl apply -f "$EXAMPLES_PATH/$CR_FILENAME"

  sleep 5
  
  # 3. Create a unique output directory for this run to avoid overwriting
  # or ensure the python script handles unique naming based on an env var.
  # Here, I'm passing the TAG as an environment variable to the container.
  
  echo "Starting simulation container..."
  
  # Run the simulation synchronously (removed -d) so the script waits for it to finish.
  # If you need it detached, we have to add a wait logic.
  docker run --rm \
    --name "simulation-$SIMULATION_DESCRIPTION" \
    --network host \
    -v ~/.kube/config:/root/.kube/config \
    -v "$(pwd)/outputs_simulation/$SIMULATION_DESCRIPTION-$CR_FILENAME:/app/outputs_simulation" \
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
