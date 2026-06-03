"""
评分对比脚本：用 SGLang (Qwen3.5-9B) 做 judge，对比 baseline vs trained
输出：每条分数 + 汇总统计（科室级别）
"""
import json, httpx, time, re
from pathlib import Path
from collections import defaultdict

BASELINE_FILE = "/workspace/eval_results/baseline_responses_tf.jsonl"
TRAINED_FILE  = "/workspace/eval_results/trained_responses.jsonl"
OUT_FILE      = "/workspace/eval_results/score_comparison_tf.jsonl"
SGLANG_URL    = "http://localhost:20000"

JUDGE_PROMPT = """你是医学评估专家。请对以下医学问答进行评分。

【问题】
{question}

【参考答案】
{reference}

【待评分回答】
{response}

请从以下维度评分（每项1-5分）：
1. 准确性：医学事实是否正确
2. 完整性：是否涵盖了关键要点
3. 简洁性：是否简洁清晰不冗余

只输出三个数字，用逗号分隔，如：4,3,5"""

SCORE_API_KEY = "sk-eb9bXqd0mJBUfeXkA9EfDaAa03Cb4692B59aB89471BdBfDd"
SCORE_API_URL = "http://8.219.115.209:6600/v1/chat/completions"
SCORE_MODEL   = "gpt-5.4"

def judge_response(question, reference, response):
    for attempt in range(3):
        try:
            r = httpx.post(SCORE_API_URL, json={
                "model": SCORE_MODEL,
                "messages": [{"role": "user", "content": JUDGE_PROMPT.format(
                    question=question[:300], reference=reference[:300], response=response[:400])}],
                "max_completion_tokens": 30, "temperature": 0,
            }, headers={"Authorization": f"Bearer {SCORE_API_KEY}"}, timeout=30)
            text = r.json()["choices"][0]["message"]["content"].strip()
            nums = re.findall(r"\d+", text)
            if len(nums) >= 3:
                scores = [int(n) for n in nums[:3]]
                if all(1 <= s <= 5 for s in scores):
                    return scores
        except Exception as e:
            time.sleep(2)
    return [3, 3, 3]

baseline = {r["idx"]: r for r in (json.loads(l) for l in open(BASELINE_FILE, encoding="utf-8"))}
trained  = {r["idx"]: r for r in (json.loads(l) for l in open(TRAINED_FILE,  encoding="utf-8"))}
common_ids = sorted(set(baseline) & set(trained))
print(f"Scoring {len(common_ids)} pairs...", flush=True)

results = []
Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for i, idx in enumerate(common_ids):
        b = baseline[idx]
        t = trained[idx]
        b_scores = judge_response(b["instruction"], b["reference"], b["response"])
        t_scores = judge_response(t["instruction"], t["reference"], t["response"])
        record = {
            "idx": idx, "dept": b.get("dept", ""),
            "baseline_scores": b_scores, "trained_scores": t_scores,
            "baseline_avg": round(sum(b_scores)/3, 2),
            "trained_avg":  round(sum(t_scores)/3, 2),
            "delta": round(sum(t_scores)/3 - sum(b_scores)/3, 2),
        }
        results.append(record)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        if (i+1) % 20 == 0 or i == 0:
            print(f"  [{i+1:3d}/{len(common_ids)}] dept={record['dept']:8s} delta={record['delta']:+.2f}", flush=True)

avg_b = sum(r["baseline_avg"] for r in results) / len(results)
avg_t = sum(r["trained_avg"]  for r in results) / len(results)
delta = avg_t - avg_b

print("\n" + "="*50, flush=True)
print(f"RESULTS ({len(results)} pairs):", flush=True)
print(f"  Baseline avg score:  {avg_b:.3f}", flush=True)
print(f"  Trained  avg score:  {avg_t:.3f}", flush=True)
print(f"  Delta:               {delta:+.3f}", flush=True)

dept_b = defaultdict(list)
dept_t = defaultdict(list)
for r in results:
    dept_b[r["dept"]].append(r["baseline_avg"])
    dept_t[r["dept"]].append(r["trained_avg"])
print("\nPer-department:", flush=True)
for dept in sorted(dept_b):
    b_d = sum(dept_b[dept])/len(dept_b[dept])
    t_d = sum(dept_t[dept])/len(dept_t[dept])
    print(f"  {dept:12s}: {b_d:.2f} -> {t_d:.2f}  ({t_d-b_d:+.2f})", flush=True)
print("="*50, flush=True)
