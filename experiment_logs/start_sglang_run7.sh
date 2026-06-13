#!/bin/bash
# Run7: Qwen3.5-32B teacher on GPU1; GPU0 for Qwen3.5-9B student
export PATH=/usr/local/miniconda3/envs/py312/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export CUDA_HOME=/usr/local/cuda-12.8
PYTHON=/usr/local/miniconda3/envs/py312/bin/python

pkill -f sglang 2>/dev/null
sleep 2
mkdir -p /workspace/logs

CUDA_VISIBLE_DEVICES=1 nohup $PYTHON -m sglang.launch_server \
    --model-path /workspace/Qwen3.5-32B \
    --host 0.0.0.0 \
    --port 20000 \
    --mem-fraction-static 0.82 \
    --trust-remote-code \
    --served-model-name Qwen3.5-32B \
    --attention-backend triton \
    --sampling-backend pytorch \
    --disable-cuda-graph \
    > /workspace/logs/sglang_run7.log 2>&1 &
echo "SGLang Qwen3.5-32B teacher PID: $!"
