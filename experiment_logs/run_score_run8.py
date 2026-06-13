import json, httpx, time, re
from pathlib import Path
from collections import defaultdict

BASELINE_FILE = "/workspace/eval_results/baseline_qwen3_8b.jsonl"
TRAINED_FILE  = "/workspace/eval_results/trained_qwen3_8b_run8.jsonl"
OUT_FILE      = "/workspace/eval_results/score_comparison_run8.jsonl"
SCORE_API_KEY = "sk-VzP164mp8fXCt7p2089dD47d35Aa4fA8A730F1E0A61dF77b"
SCORE_API_URL = "https://one-api.infox-med.com/v1/chat/completions"
SCORE_MODEL   = "gpt-5.4"

def judge_response(question, reference, response):
    prompt = question[:300] + "\n\n" + reference[:300] + "\n\n" + response[:400] + "\n\n4,3,5"
    for attempt in range(3):
        try:
            r = httpx.post(SCORE_API_URL, json={
                "model": SCORE_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_completion_tokens": 30, "temperature": 0,
            }, headers={"Authorization": "Bearer " + SCORE_API_KEY}, timeout=30)
            text = r.json()["choices"][0]["message"]["content"].strip()
            nums = re.findall(r"\d+", text)
            if len(nums) >= 3:
                scores = [int(n) for n in nums[:3]]
                if all(1 <= s <= 5 for s in scores):
                    return scores
        except Exception:
            time.sleep(2)
    return [3, 3, 3]

baseline = {r["idx"]: r for r in (json.loads(l) for l in open(BASELINE_FILE, encoding="utf-8"))}
trained  = {r["idx"]: r for r in (json.loads(l) for l in open(TRAINED_FILE,  encoding="utf-8"))}
common_ids = sorted(set(baseline) & set(trained))
print("Scoring " + str(len(common_ids)) + " pairs...", flush=True)

results = []
Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for i, idx in enumerate(common_ids):
        b = baseline[idx]
        t = trained[idx]
        b_scores = judge_response(b["instruction"], b["reference"], b["response"])
        t_scores = judge_response(t["instruction"], t["reference"], t["response"])
        dept = b.get("dept", "")
        b_avg = round(sum(b_scores)/3, 2)
        t_avg = round(sum(t_scores)/3, 2)
        record = {"idx": idx, "dept": dept,
            "baseline_scores": b_scores, "trained_scores": t_scores,
            "baseline_avg": b_avg, "trained_avg": t_avg,
            "delta": round(t_avg - b_avg, 2)}
        results.append(record)
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        if (i+1) % 20 == 0 or i == 0:
            print("  [" + str(i+1) + "/" + str(len(common_ids)) + "] dept=" + dept + " delta=" + str(record["delta"]), flush=True)

avg_b = sum(r["baseline_avg"] for r in results) / len(results)
avg_t = sum(r["trained_avg"]  for r in results) / len(results)
delta = avg_t - avg_b
print("=" * 50, flush=True)
print("RESULTS: baseline=" + str(round(avg_b,3)) + " trained=" + str(round(avg_t,3)) + " delta=" + str(round(delta,3)), flush=True)

dept_b = defaultdict(list)
dept_t = defaultdict(list)
for r in results:
    dept_b[r["dept"]].append(r["baseline_avg"])
    dept_t[r["dept"]].append(r["trained_avg"])
for dept in sorted(dept_b):
    b_d = sum(dept_b[dept])/len(dept_b[dept])
    t_d = sum(dept_t[dept])/len(dept_t[dept])
    print("  " + dept + ": " + str(round(b_d,2)) + " -> " + str(round(t_d,2)) + " (" + str(round(t_d-b_d,2)) + ")", flush=True)
print("=" * 50, flush=True)
