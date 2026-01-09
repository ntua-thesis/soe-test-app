# Profiling

run the app:

```
docker build -t load-test-runner:0.0.2 .
docker tag load-test-runner:0.0.2 nexus.lefto.org/docker/load-test-runner:0.0.2
docker push nexus.lefto.org/docker/load-test-runner:0.0.2
```

```
docker run --rm \
  --network host \
  -v ~/.kube/config:/root/.kube/config \
  -v $(pwd)/results:/app/results \
  -v $(pwd)/experiment_runner.py:/app/experiment_runner.py \
  -v $(pwd)/../chart:/chart \
  load-test-runner:0.0.2 \
  python -u experiment_runner.py
```

```
docker run --rm -it \
  --network host \
  -v ~/.kube/config:/root/.kube/config \
  -v $(pwd)/continuous_load.py:/app/continuous_load.py \
  -v $(pwd)/../chart:/chart \
  load-test-runner:0.0.2 \
  python -u continuous_load.py
```

```
docker run -d --rm \
  --name my-load-test \
  --network host \
  -v ~/.kube/config:/root/.kube/config \
  -v "$(pwd)/results:/app/results" \
  -v "$(pwd)/experiment_runner.py:/app/experiment_runner.py" \
  -v "$(pwd)/../chart:/chart" \
  nexus.lefto.org/docker/load-test-runner:0.0.2 > container_id.txt && \
docker logs -f $(cat container_id.txt) > log.txt 2>&1 &
```

```
docker run --rm -it \
  --name simulation \
  --network host \
  -v ~/.kube/config:/root/.kube/config \
  -v "$(pwd)/outputs_simulation:/app/outputs_simulation" \
  -v "$(pwd)/simulate.py:/app/simulate.py" \
  -v "/path/to/timestamps.txt:/app/timestamps.txt" \
  nexus.lefto.org/docker/load-test-runner:0.0.2 \
  python -u simulate.py
```

```
docker run --rm \
  -v "$(pwd)/simulations/0.2.0-0.1.1-ahp-only:/app/outputs_simulation" \
  -v "$(pwd)/create_graphs.py:/app/create_graphs.py" \
  model-runner:0.0.2 \
  python -u create_graphs.py
```

```
docker run --rm \
  -v "$(pwd)/simulations/0.2.0-0.1.1-ahp-only/metrics:/app/input_ahp/metrics" \
  -v "$(pwd)/simulations/0.2.0-0.1.1-if-not-updated/metrics:/app/input_full/metrics" \
  -v "$(pwd)/simulations/graphs/0.2.0-0.1.1-ahp-only-vs-0.2.0-0.1.1-if-not-updated:/app/output" \
  -v "$(pwd)/comparison_graphs.py:/app/comparison_graphs.py" \
  model-runner:0.0.2 \
  python -u comparison_graphs.py
```
