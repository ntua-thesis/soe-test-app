#!/bin/bash

TAGS=(
  # "0.1.1-ahp-only"
  "0.2.0-if-not-updated"
  # "0.1.1-independent"
  "0.2.0-knn-after"
  "0.2.0-three-to-one"
)

SERVER_TAG="0.1.2"
OPERATOR_TAG="0.3.0"

for TAG in "${TAGS[@]}"; do
    DIR="$OPERATOR_TAG-$TAG-server-$SERVER_TAG"

    scp -r ssh.lefto.org:/home/lefto/soe-test-app/profiling/outputs_simulation/$DIR/ simulations/

    docker run --rm \
        -v "$(pwd)/simulations/$DIR:/app/outputs_simulation" \
        -v "$(pwd)/create_graphs.py:/app/create_graphs.py" \
        model-runner:0.0.2 \
        python -u create_graphs.py

done 