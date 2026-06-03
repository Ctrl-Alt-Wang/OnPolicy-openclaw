"""
用 transformers 直接推理 base model（无 LoRA），收集 200 条 baseline
确保和 trained_responses.jsonl 推理方式完全一致
"""
import json, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

MODEL_PATH = "/workspace/Qwen3.5-9B"
EVAL_FILE  = "/workspace/data/eval_huatuo_200.jsonl"
OUT_FILE   = "/workspace/eval_results/baseline_responses_tf.jsonl"

Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)

print("Loading base model (no LoRA)...", flush=True)
bnb = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True
)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, quantization_config=bnb, device_map="cuda", trust_remote_code=True
)
model.eval()
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
print("Model ready.", flush=True)

eval_data = [json.loads(l) for l in open(EVAL_FILE, encoding="utf-8")]
SYSTEM = "你是一个专业的医学助手，请简洁准确地回答医学问题。"
errors = 0

with open(OUT_FILE, "w", encoding="utf-8") as f:
    for i, item in enumerate(eval_data):
        try:
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": item["instruction"]},
            ]
            text = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
                enable_thinking=False
            )
            inputs = tokenizer(text, return_tensors="pt").to("cuda")
            with torch.no_grad():
                out = model.generate(
                    **inputs, max_new_tokens=300, temperature=None,
                    do_sample=False, pad_token_id=tokenizer.eos_token_id
                )
            reply = tokenizer.decode(
                out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
            ).strip()
        except Exception as e:
            errors += 1
            reply = f"[ERROR: {e}]"

        record = {"idx": i, "instruction": item["instruction"],
                  "reference": item["output"], "response": reply,
                  "dept": item.get("dept", "")}
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()

        if (i+1) % 10 == 0 or i == 0:
            print(f"  [{i+1:3d}/200] {item.get('dept','?'):8s} | {reply[:60].replace(chr(10),' ')}...", flush=True)

print(f"\nDone! 200 total, {errors} errors -> {OUT_FILE}", flush=True)
