#!/bin/bash
# Tail logs from all 10 hermes-innovation containers with container name prefix
# Usage:
#   bash tail_all_hermes.sh              # follow all
#   bash tail_all_hermes.sh | grep -i error  # filter errors
#   bash tail_all_hermes.sh | grep "sid-xxx" # filter by session

PIDS=()

cleanup() {
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null
    done
    wait 2>/dev/null
    exit 0
}
trap cleanup INT TERM

for i in $(seq 0 9); do
    idx=$(printf "%02d" "$i")
    name="hermes-innovation-$idx"
    if docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        docker logs -f "$name" 2>&1 | sed "s/^/[innovation-$i] /" &
        PIDS+=($!)
    else
        echo "[innovation-$i] container not running, skipping"
    fi
done

if [ ${#PIDS[@]} -eq 0 ]; then
    echo "No hermes-innovation containers found."
    exit 1
fi

echo "Tailing ${#PIDS[@]} containers. Press Ctrl+C to stop."
wait
