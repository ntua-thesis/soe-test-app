# Knn

run the app:

```
docker build -t model-runner:0.0.2 .
docker tag load-test-runner:0.0.2 nexus.lefto.org/docker/model-runner:0.0.2
docker push nexus.lefto.org/docker/model-runner:0.0.2
```

```
docker run --rm \
  -v $(pwd)/../profiling/results-64bit-n500000:/app/results \
  -v $(pwd):/app \
  model-runner:0.0.2 \
  python -u create_dataset.py
```

```
docker run --rm \
  -v $(pwd):/app \
  model-runner:0.0.2 \
  python -u random_forest.py
```

```
docker run --rm \
  -v $(pwd):/app \
  model-runner:0.0.2 \
  python -u knn.py
```

```
docker run --rm \
  -v $(pwd):/app \
  model-runner:0.0.2 \
  python -u visualize.py
```
