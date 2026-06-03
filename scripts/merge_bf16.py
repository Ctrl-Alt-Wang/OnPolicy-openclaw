"""
把 LoRA adapter 合并到 bf16 base model，保存为 SGLang 可加载的格式
"""
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

MODEL_PATH  = "/workspace/Qwen3.5-9B"
LORA_PATH   = "/workspace/lora_checkpoints/latest"
MERGED_PATH = "/workspace/Qwen3.5-9B-trained-bf16"

print("Loading base model in bf16...", flush=True)
base = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="cuda",
    trust_remote_code=True,
)
print("Loading LoRA adapter...", flush=True)
model = PeftModel.from_pretrained(base, LORA_PATH)

print("Merging...", flush=True)
model = model.merge_and_unload()

print(f"Saving to {MERGED_PATH} ...", flush=True)
model.save_pretrained(MERGED_PATH, safe_serialization=True)
tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
tokenizer.save_pretrained(MERGED_PATH)

print("Done.", flush=True)
