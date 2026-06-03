"""
训练前/后收集模型回答（边收边写，实时可见进度）
"""
import json, httpx, argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--eval-file",  default="/workspace/data/eval_huatuo_200.jsonl")
parser.add_argument("--out",        default="/workspace/eval_results/baseline_responses.jsonl")
parser.add_argument("--sglang-url", default="http://localhost:20000")
args = parser.parse_args()

Path(args.out).parent.mkdir(parents=True, exist_ok=True)
eval_data = [json.loads(l) for l in open(args.eval_file, encoding="utf-8")]
print(f"评测集：{len(eval_data)} 条", flush=True)
print(f"输出到：{args.out}", flush=True)

SYSTEM = "你是一个专业的医学助手，请简洁准确地回答医学问题。"
errors = 0

# 边收边写，追加模式
with open(args.out, "w", encoding="utf-8") as f:
    for i, item in enumerate(eval_data):
        try:
            r = httpx.post(
                f"{args.sglang_url}/v1/chat/completions",
                json={
                    "model": "Qwen3.5-9B",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user",   "content": item["instruction"]},
                    ],
                    "max_tokens": 500,
                    "temperature": 0,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
                timeout=120,
            )
            r.raise_for_status()
            reply = r.json()["choices"][0]["message"]["content"] or ""
        except Exception as e:
            errors += 1
            reply = f"[ERROR: {e}]"

        record = {
            "idx":         i,
            "instruction": item["instruction"],
            "reference":   item["output"],
            "response":    reply,
            "dept":        item.get("dept", ""),
        }
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

        if (i + 1) % 10 == 0 or i == 0:
            print(f"  [{i+1:3d}/200] {item.get('dept','?'):8s} | {reply[:50].replace(chr(10),' ')}...", flush=True)

print(f"\n完成！共 {len(eval_data)} 条，失败 {errors} 条", flush=True)
print(f"保存：{args.out}", flush=True)
