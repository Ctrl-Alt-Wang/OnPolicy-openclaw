"""
Self-OPD (OPCD) 完整训练脚本
训练数据：/workspace/data/train_huatuo_2000.jsonl
- Turn 1：把 instruction 发给 student
- Turn 2：把 output（参考答案）作为 next_state 发给 OPD server
- Judge 评估 student 回答 vs 参考答案，提取 hint
- Teacher（同模型 + hint）计算 logprobs
- QLoRA 梯度更新

用法：
  python run_self_opd.py --batch-size 16 --lr 5e-7
"""
import argparse, sys, os, queue, threading, time, torch, logging, uuid, json, random
import wandb
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument("--train-file",  default="/workspace/data/train_huatuo_2000.jsonl")
parser.add_argument("--save-dir",    default="/workspace/lora_checkpoints")
parser.add_argument("--batch-size",  type=int,   default=16)
parser.add_argument("--lr",          type=float, default=5e-7)
parser.add_argument("--opd-port",    type=int,   default=30010)
parser.add_argument("--max-samples", type=int,   default=0, help="0=全跑")
parser.add_argument("--save-every",  type=int,   default=5,  help="每N步保存一次")
args = parser.parse_args()

# WandB 初始化
os.environ["WANDB_BASE_URL"] = "http://103.139.212.228:3005"
os.environ["WANDB_API_KEY"]  = "local-f2ca8cd44276ac92ca0a2c12641a6902beb6847d"
wandb.init(
    project="medical-opd",
    name=f"qwen3.5-9b-opcd-lr{args.lr}-bs{args.batch_size}",
    config={
        "model": "Qwen3.5-9B",
        "method": "OPCD",
        "lr": args.lr,
        "batch_size": args.batch_size,
        "max_len": 256,
        "train_samples": 2000,
    },
)

MODEL_PATH = "/workspace/Qwen3.5-9B"
sys.path.insert(0, "/workspace/OnPolicy/OpenClaw-RL/slime")
sys.path.insert(0, "/workspace/OnPolicy/OpenClaw-RL/openclaw-opd")

# ─── 1. 加载训练数据 ────────────────────────────────────────────
logger.info("加载训练数据...")
train_data = [json.loads(l) for l in open(args.train_file, encoding="utf-8")]
if args.max_samples > 0:
    random.shuffle(train_data)
    train_data = train_data[:args.max_samples]
logger.info(f"训练集：{len(train_data)} 条")

# 科室分布
from collections import Counter
dist = Counter(d.get("dept", "?") for d in train_data)
for dept, cnt in sorted(dist.items(), key=lambda x: -x[1]):
    logger.info(f"  {dept}: {cnt}")

# ─── 2. 启动 OPD server ─────────────────────────────────────────
from openclaw_opd_api_server import OpenClawOPDAPIServer

class OPDArgs:
    hf_checkpoint      = MODEL_PATH
    sglang_router_ip   = "127.0.0.1"
    sglang_router_port = 20000
    prm_enable         = True
    prm_router_ip      = "127.0.0.1"
    prm_router_port    = 20001
    prm_m              = 3
    prm_temperature    = 0.7
    prm_max_new_tokens = 1024
    distill_topk       = 0

import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ.update({
    "HOST": "0.0.0.0",
    "PORT": str(args.opd_port),
    "SERVED_MODEL_NAME": "Qwen3.5-9B",
    "SGLANG_API_KEY": "",
    "OPENCLAW_RECORD_ENABLED": "1",
    "OPENCLAW_RECORD_FILE": "/workspace/logs/opd_full_record.jsonl",
    "OPENCLAW_EVAL_MODE": "1",
})

output_queue       = queue.Queue(maxsize=100000)
submission_enabled = threading.Event()
submission_enabled.set()

logger.info(f"启动 OPD server (port {args.opd_port})...")
opd_server = OpenClawOPDAPIServer(OPDArgs(), output_queue, submission_enabled)
opd_server.start()

import httpx
for _ in range(20):
    time.sleep(2)
    try:
        if httpx.get(f"http://localhost:{args.opd_port}/healthz", timeout=3).status_code == 200:
            logger.info("OPD server 就绪")
            break
    except Exception:
        pass

# ─── 3. 对话线程（把训练数据发给 OPD server）─────────────────────
SYSTEM = "你是一个专业的医学助手，请简洁准确地回答医学问题。"
OPD_URL = f"http://localhost:{args.opd_port}"

def send_training_conversations():
    """
    Turn 1：发 instruction（问题）→ student 生成回答
    Turn 2：把 output（华佗参考答案的前300字）作为 next_state
            judge 会评估：student 回答 vs 参考答案，差距在哪里
    """
    logger.info(f"开始发送 {len(train_data)} 条对话...")
    ok = err = 0
    for i, item in enumerate(train_data):
        sid = str(uuid.uuid4())
        try:
            q = item["instruction"]
            ref = item["output"][:300]  # 参考答案截取前300字作为 next_state

            # Turn 1：发问题
            msgs1 = [
                {"role": "system",  "content": SYSTEM},
                {"role": "user",    "content": q},
            ]
            r1 = httpx.post(
                f"{OPD_URL}/v1/chat/completions",
                json={"model": "Qwen3.5-9B", "messages": msgs1,
                      "max_tokens": 400, "temperature": 0.7,
                      "chat_template_kwargs": {"enable_thinking": False}},
                headers={"X-Session-Id": sid, "X-Turn-Type": "main"},
                timeout=90,
            )
            r1.raise_for_status()
            student_reply = r1.json()["choices"][0]["message"]["content"] or ""

            # Turn 2：把参考答案作为 next_state（让 judge 看到差距）
            # 格式：模拟"医生给出了更好的回答"作为下一条消息
            msgs2 = msgs1 + [
                {"role": "assistant", "content": student_reply},
                {"role": "user",      "content": f"参考一下这个更完整的回答：{ref}"},
            ]
            r2 = httpx.post(
                f"{OPD_URL}/v1/chat/completions",
                json={"model": "Qwen3.5-9B", "messages": msgs2,
                      "max_tokens": 200, "temperature": 0.7,
                      "chat_template_kwargs": {"enable_thinking": False}},
                headers={"X-Session-Id": sid, "X-Turn-Type": "main",
                         "X-Session-Done": "true"},
                timeout=90,
            )
            r2.raise_for_status()
            ok += 1
            if (i + 1) % 100 == 0:
                logger.info(f"  对话进度: {i+1}/{len(train_data)}  成功={ok} 失败={err}")
        except Exception as e:
            err += 1
            if err <= 5:
                logger.warning(f"  第{i+1}条失败: {e}")
        time.sleep(0.2)
    logger.info(f"对话全部发送完毕：成功={ok} 失败={err}")

conv_thread = threading.Thread(target=send_training_conversations, daemon=True)
conv_thread.start()

# ─── 4. 加载模型（QLoRA）───────────────────────────────────────
logger.info("加载 QLoRA 模型...")
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, PeftModel

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
bnb_cfg = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

lora_latest = f"{args.save_dir}/latest"
base = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH, quantization_config=bnb_cfg, device_map="cuda", trust_remote_code=True)
base = prepare_model_for_kbit_training(base)
if os.path.exists(lora_latest):
    model = PeftModel.from_pretrained(base, lora_latest, is_trainable=True)
    logger.info(f"续训：加载已有 checkpoint {lora_latest}")
else:
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, quantization_config=bnb_cfg, device_map="cuda", trust_remote_code=True)
    base = prepare_model_for_kbit_training(base)
    lora_cfg = LoraConfig(
        r=16, lora_alpha=32,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
    )
    model = get_peft_model(base, lora_cfg)
    logger.info("新建 QLoRA checkpoint")

model.print_trainable_parameters()
model.train()
optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

# ─── 5. 训练循环 ────────────────────────────────────────────────
MAX_LEN    = 256
step_count = 0
total_loss_sum = 0.0
all_losses = []

logger.info(f"等待 Sample 进入队列（batch_size={args.batch_size}）...")

while True:
    # 收集一个 batch 的 Sample
    batch = []
    deadline = time.time() + 300  # 最多等 5 分钟
    while len(batch) < args.batch_size and time.time() < deadline:
        try:
            _, group = output_queue.get(timeout=5)
            batch.extend(group)
        except queue.Empty:
            if not conv_thread.is_alive() and output_queue.empty():
                break

    if not batch:
        if not conv_thread.is_alive():
            logger.info("对话线程结束且队列为空，训练完成")
            break
        continue

    # 梯度更新
    optimizer.zero_grad()
    total_loss = None
    token_count = 0

    for s in batch[:args.batch_size]:
        ids       = list(s.tokens)[:MAX_LEN]
        resp_len  = min(s.response_length, MAX_LEN)
        mask      = list(s.loss_mask)[:resp_len]
        slps      = list(s.rollout_log_probs)[:resp_len]
        tlps_raw  = s.teacher_log_probs
        tlps      = (tlps_raw.tolist() if hasattr(tlps_raw, "tolist") else list(tlps_raw))[:resp_len]

        id_t = torch.tensor([ids], dtype=torch.long).cuda()
        with torch.cuda.amp.autocast(dtype=torch.bfloat16):
            out    = model(input_ids=id_t)
            logits = out.logits[0]

        prompt_len = len(ids) - resp_len
        for t, (m, slp, tlp) in enumerate(zip(mask, slps, tlps)):
            if m == 0:
                continue
            pos = prompt_len + t - 1
            if pos < 0 or pos >= logits.shape[0]:
                continue
            tok_id     = ids[prompt_len + t] if (prompt_len + t) < len(ids) else 0
            student_lp = torch.nn.functional.log_softmax(logits[pos], dim=-1)[tok_id]
            teacher_lp = torch.tensor(float(tlp), device="cuda")
            step_loss  = -(teacher_lp - student_lp)
            total_loss = step_loss if total_loss is None else total_loss + step_loss
            token_count += 1

    if total_loss is None or token_count == 0:
        logger.warning("本 batch 无有效 token，跳过")
        continue

    avg_loss = total_loss / token_count
    avg_loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    optimizer.step()

    step_count     += 1
    loss_val        = avg_loss.item()
    total_loss_sum += loss_val
    all_losses.append(round(loss_val, 4))

    logger.info(
        f"Step {step_count:4d} | loss={loss_val:.4f} | "
        f"avg_loss={total_loss_sum/step_count:.4f} | tokens={token_count} | "
        f"queue={output_queue.qsize()}"
    )
    wandb.log({
        "loss": loss_val,
        "avg_loss": total_loss_sum / step_count,
        "tokens": token_count,
        "queue_size": output_queue.qsize(),
        "samples_collected": step_count * args.batch_size,
    }, step=step_count)

    # 定期保存
    if step_count % args.save_every == 0:
        ckpt = f"{args.save_dir}/step_{step_count}"
        os.makedirs(ckpt, exist_ok=True)
        model.save_pretrained(ckpt)
        logger.info(f"  已保存 checkpoint: {ckpt}")

# ─── 6. 保存最终结果 ────────────────────────────────────────────
os.makedirs(f"{args.save_dir}/latest", exist_ok=True)
model.save_pretrained(f"{args.save_dir}/latest")

print()
wandb.finish()
print("=" * 60)
print("训练完成！")
print(f"  总步数:  {step_count}")
print(f"  Loss 列表: {all_losses}")
if len(all_losses) >= 2:
    trend = "↓ 下降" if all_losses[-1] < all_losses[0] else "→ 持平/上升"
    print(f"  Loss 趋势: {all_losses[0]} → {all_losses[-1]}  {trend}")
print(f"  最终 checkpoint: {args.save_dir}/latest")
print("=" * 60)
