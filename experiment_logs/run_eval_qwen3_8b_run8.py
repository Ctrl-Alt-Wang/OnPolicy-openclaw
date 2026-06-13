import json, torch
from pathlib import Path
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

MODEL_PATH = "/workspace/Qwen3-8B"
LORA_PATH  = "/workspace/lora_ckpt_qwen3_8b_run8_nojudge/latest"
EVAL_FILE  = "/workspace/data/eval_huatuo_200.jsonl"
OUT_FILE   = "/workspace/eval_results/trained_qwen3_8b_run8.jsonl"
Path(OUT_FILE).parent.mkdir(parents=True, exist_ok=True)

print("Loading Qwen3-8B + Run8 LoRA...", flush=True)
bnb = BitsAndBytesConfig(
    load_in_4bit=True, bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True)
base = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, quantization_config=bnb, device_map="cuda", trust_remote_code=True)
model = PeftModel.from_pretrained(base, LORA_PATH)
model.eval()
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
print("Model ready.", flush=True)

eval_data = [json.loads(l) for l in open(EVAL_FILE, encoding="utf-8")]
SYSTEM = "你是一个专业的医学助手，请准确地回答医学问题。"

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
                chat_template_kwargs={"enable_thinking": False})
            ids = tokenizer(text, return_tensors="pt").input_ids.cuda()
            with torch.no_grad():
                out = model.generate(ids, max_new_tokens=600, temperature=0.01,
                                     do_sample=False, pad_token_id=tokenizer.eos_token_id)
            resp = tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True)
            rec = {"idx": i, "instruction": item["instruction"],
                   "reference": item.get("output",""), "response": resp}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if (i+1) % 20 == 0:
                print(f"  {i+1}/200 done", flush=True)
        except Exception as e:
            errors += 1
            print(f"  [{i}] error: {e}", flush=True)

print(f"Done. errors={errors}", flush=True)
