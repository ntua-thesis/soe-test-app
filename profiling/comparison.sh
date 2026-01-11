#!/bin/bash

TAGS=(
  "0.1.1-ahp-only"
  "0.2.0-if-not-updated"
  "0.1.1-independent"
  "0.2.0-knn-after"
  "0.2.0-three-to-one"
)

SERVER_TAG="0.1.2"
OPERATOR_TAG="0.3.0"

TAG_2="0.2.0-${TAGS[0]}"

TAG_AHP="$OPERATOR_TAG-${TAGS[0]}-server-$SERVER_TAG"
TAG_FULL="$OPERATOR_TAG-${TAGS[4]}-server-$SERVER_TAG"

echo creating $TAG_AHP-vs-$TAG_FULL

docker run --rm \
  -v "$(pwd)/simulations/$TAG_AHP/metrics:/app/input_ahp/metrics" \
  -v "$(pwd)/simulations/$TAG_FULL/metrics:/app/input_full/metrics" \
  -v "$(pwd)/simulations/graphs/$TAG_AHP-vs-$TAG_FULL:/app/output" \
  -v "$(pwd)/comparison_graphs.py:/app/comparison_graphs.py" \
  model-runner:0.0.2 \
  python -u comparison_graphs.py