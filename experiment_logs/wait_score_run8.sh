#!/bin/bash
while true; do
  cnt=$(cat /workspace/eval_results/trained_qwen3_8b_run8.jsonl 2>/dev/null | wc -l)
  echo "$(date '+%H:%M') lines=$cnt/200"
  if [ "$cnt" -ge 200 ]; then
    echo "Eval done! Scoring..."
    /usr/local/miniconda3/envs/py312/bin/python /workspace/run_score_run8.py
    echo "Scoring done."
    break
  fi
  sleep 120
done
