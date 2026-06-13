#!/bin/bash
# Qwen3-32B BF16 teacher on GPU1; GPU0 for Qwen3-8B student
export PATH=/usr/local/miniconda3/envs/py312/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export CUDA_HOME=/usr/local/cuda-12.8
PYTHON=/usr/local/miniconda3/envs/py312/bin/python
pkill -f sglang 2>/dev/null
sleep 2
mkdir -p /workspace/logs
CUDA_VISIBLE_DEVICES=1 nohup $PYTHON -m sglang.launch_server \n    --model-path /workspace/Qwen3-32B \n    --host 0.0.0.0 \n    --port 20000 \n    --mem-fraction-static 0.82 \n    --trust-remote-code \n    --served-model-name Qwen3-32B \n    --attention-backend triton \n    --sampling-backend pytorch \n    --disable-cuda-graph \n    > /workspace/logs/sglang_32b.log 2>&1 &
echo "SGLang Qwen3-32B teacher PID: $!"
