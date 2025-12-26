# Profiling

run the app:

```
docker build -t load-test-runner:0.0.1 .
```

```
docker run --rm \
  --network host \
  -v ~/.kube/config:/root/.kube/config \
  -v $(pwd)/results:/app/results \
  -v $(pwd)/experiment_runner.py:/app/experiment_runner.py \
  -v $(pwd)/../chart:/chart \
  load-test-runner:0.0.1
```
