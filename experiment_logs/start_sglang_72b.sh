#!/bin/bash
mkdir -p /workspace/logs

# FP8 online quantization: peak GPU mem = FP8 weights(36GB) + current tensor(~0.5GB) = ~37GB per GPU
# mem-fraction-static=0.55 -> allocates 44GB per GPU: 37GB loading peak + 7GB KV cache
# GPU0 remaining for student: 80-44=36GB

CUDA_VISIBLE_DEVICES=0,1 nohup /usr/local/miniconda3/envs/py312/bin/python -m sglang.launch_server     --model-path /model/ModelScope/Qwen/Qwen2.5-72B-Instruct     --host 0.0.0.0 --port 20000     --tensor-parallel-size 2     --quantization fp8     --mem-fraction-static 0.55     --context-length 2048     --trust-remote-code     --served-model-name Qwen2.5-72B-Instruct     --disable-cuda-graph     > /workspace/logs/sglang_72b.log 2>&1 &

echo "SGLang PID: $!"
