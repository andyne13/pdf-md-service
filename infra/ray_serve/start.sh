#!/bin/bash
set -e

ray start --head --dashboard-host=0.0.0.0 --num-gpus=1

# Wait for Ray to be ready
for i in $(seq 1 30); do
    if ray status >/dev/null 2>&1; then
        echo "Ray is ready."
        break
    fi
    echo "Waiting for Ray to start... ($i/30)"
    sleep 1
done

# serve run blocks and streams all logs to stdout
exec serve run /app/serve_config.yaml
