#!/bin/bash
echo "Waiting for eval (200 lines)..."
while true; do
    cnt=0
    echo "17:48 lines=$cnt/200"
    if [ "$cnt" -ge 200 ]; then
        echo "Eval done! Starting scoring..."
        /usr/local/miniconda3/envs/py312/bin/python /workspace/run_score_run8.py
        echo "Scoring done."
        break
    fi
    sleep 120
done
