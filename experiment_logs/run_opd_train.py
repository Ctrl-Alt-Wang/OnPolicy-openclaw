"""
OPD 完整训练验证脚本（数据收集 + 训练一体化）
在同一进程内运行 OPD server，收集 Sample，做 LoRA 梯度更新

用法:
  python run_opd_train.py --num 50   # 先跑 50 条
  python run_opd_train.py --num 100  # 再跑 100 条
"""
import argparse, asyncio, sys, os, queue, threading, time, torch, logging, uuid, json

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser()
parser.add_argument("--num",        type=int, default=50,  help="对话条数")
parser.add_argument("--batch-size", type=int, default=16,  help="训练 batch（低阈值方便测试）")
parser.add_argument("--lr",         type=float, default=5e-7)
parser.add_argument("--opd-port",   type=int, default=30002, help="本次用的 OPD 端口（避开已运行的 30000）")
parser.add_argument("--save-dir",   default="/workspace/lora_checkpoints")
args = parser.parse_args()

sys.path.insert(0, "/workspace/OnPolicy/OpenClaw-RL/slime")
sys.path.insert(0, "/workspace/OnPolicy/OpenClaw-RL/openclaw-opd")

MODEL_PATH = "/workspace/Qwen3.5-9B"

# ─── 1. 启动 OPD server ─────────────────────────────────────
from openclaw_opd_api_server import OpenClawOPDAPIServer

class OPDArgs:
    hf_checkpoint      = MODEL_PATH
    sglang_router_ip   = "127.0.0.1"
    sglang_router_port = 20000
    prm_enable         = True
    prm_router_ip      = "127.0.0.1"
    prm_router_port    = 20000
    prm_m              = 3
    prm_temperature    = 0.7
    prm_max_new_tokens = 2048
    distill_topk       = 0

os.environ["HOST"]  = "0.0.0.0"
os.environ["PORT"]  = str(args.opd_port)
os.environ["SERVED_MODEL_NAME"]  = "Qwen3.5-9B"
os.environ["SGLANG_API_KEY"]     = ""
os.environ["OPENCLAW_RECORD_ENABLED"] = "1"
os.environ["OPENCLAW_RECORD_FILE"]    = f"/workspace/logs/opd_train_record.jsonl"

output_queue       = queue.Queue(maxsize=100000)
submission_enabled = threading.Event()
submission_enabled.set()

logger.info(f"启动 OPD server（port {args.opd_port}）...")
opd_server = OpenClawOPDAPIServer(OPDArgs(), output_queue, submission_enabled)
opd_server.start()

# 等 server 就绪
import httpx, time as _time
for _ in range(20):
    _time.sleep(2)
    try:
        r = httpx.get(f"http://localhost:{args.opd_port}/healthz", timeout=3)
        if r.status_code == 200:
            logger.info("OPD server 就绪")
            break
    except Exception:
        pass

# ─── 2. 医学问题数据集 ────────────────────────────────────────
QUESTIONS = [
    "2型糖尿病患者血糖控制目标是什么？",
    "二甲双胍的主要禁忌症有哪些？",
    "胰岛素注射部位如何轮换？",
    "甲状腺功能亢进的典型症状是什么？",
    "糖尿病肾病如何分期？",
    "低血糖的紧急处理步骤是什么？",
    "甲状腺结节什么情况下需要穿刺活检？",
    "糖化血红蛋白HbA1c正常范围是多少？",
    "库欣综合征的主要临床表现有哪些？",
    "痛风发作期的用药原则是什么？",
    "高血压的一线治疗药物有哪些？",
    "急性心肌梗死的典型症状是什么？",
    "心房颤动患者抗凝治疗如何选择？",
    "他汀类药物的主要不良反应是什么？",
    "心力衰竭患者饮食需要注意什么？",
    "β受体阻滞剂的主要禁忌症有哪些？",
    "冠心病二级预防药物包括哪些？",
    "主动脉夹层的影像学首选检查是什么？",
    "高血压急症和亚急症如何区分？",
    "感染性心内膜炎的主要病原体有哪些？",
    "慢阻肺急性加重期的治疗原则是什么？",
    "社区获得性肺炎的经验性抗生素如何选择？",
    "哮喘发作时吸入激素和支气管扩张剂的使用顺序？",
    "肺栓塞的D-二聚体检测意义是什么？",
    "结核病的标准化疗方案是什么？",
    "胸腔积液漏出液和渗出液如何鉴别？",
    "呼吸衰竭I型和II型的区别是什么？",
    "无创呼吸机的适应证有哪些？",
    "间质性肺炎的常见病因有哪些？",
    "支气管扩张的主要治疗措施是什么？",
    "上消化道出血的紧急处理原则是什么？",
    "幽门螺旋杆菌根除治疗方案有哪些？",
    "肝硬化Child-Pugh分级包括哪些指标？",
    "急性胰腺炎的严重程度如何评估？",
    "溃疡性结肠炎和克罗恩病如何鉴别？",
    "肝性脑病的诱因有哪些？",
    "胃食管反流病的生活方式干预包括什么？",
    "急性腹泻的补液原则是什么？",
    "非酒精性脂肪性肝病的治疗要点是什么？",
    "消化道肿瘤筛查的适应人群是哪些？",
    "慢性肾脏病CKD的分期标准是什么？",
    "肾病综合征的四大临床特征是什么？",
    "高钾血症的心电图表现有哪些？",
    "急性肾损伤的常见原因有哪些？",
    "透析患者饮食限制有哪些？",
    "尿路感染上下尿路感染如何鉴别？",
    "肾小球肾炎的常见病理类型有哪些？",
    "血液透析和腹膜透析如何选择？",
    "肾脏替代治疗的指征是什么？",
    "造影剂肾病的预防措施有哪些？",
    # 额外 50 条（用于 --num 100）
    "脓毒症的诊断标准是什么？",
    "ICU 镇静镇痛的 ABCDEF bundle 是什么？",
    "机械通气的撤机指征有哪些？",
    "肺保护性通气策略的核心参数是什么？",
    "ARDS 的柏林定义标准是什么？",
    "DIC 的实验室诊断指标有哪些？",
    "过敏性休克的急救流程是什么？",
    "颅内压增高的临床表现有哪些？",
    "急性缺血性脑卒中的溶栓时间窗是多少？",
    "抗癫痫药物的选择原则是什么？",
    "帕金森病的药物治疗首选是什么？",
    "阿尔茨海默病的诊断标准是什么？",
    "重症肌无力的分型及治疗原则是什么？",
    "系统性红斑狼疮的诊断标准是什么？",
    "类风湿关节炎的疾病活动度如何评估？",
    "强直性脊柱炎的影像学表现是什么？",
    "银屑病关节炎与类风湿关节炎如何鉴别？",
    "骨质疏松症的药物治疗有哪些？",
    "急性痛风的非药物治疗措施有哪些？",
    "甲亢危象的处理原则是什么？",
    "肾上腺皮质功能减退的激素替代方案是什么？",
    "垂体瘤的手术适应证有哪些？",
    "多囊卵巢综合征的诊断标准是什么？",
    "妊娠期高血压疾病的分类是什么？",
    "产后大出血的处理流程是什么？",
    "新生儿黄疸的光疗指征是什么？",
    "儿童热性惊厥的处理原则是什么？",
    "手足口病的病原体及临床特征是什么？",
    "川崎病的诊断标准是什么？",
    "儿童营养性缺铁性贫血的治疗是什么？",
    "急性淋巴细胞白血病的分型是什么？",
    "弥漫大B细胞淋巴瘤的一线治疗方案是什么？",
    "多发性骨髓瘤的诊断标准是什么？",
    "慢性粒细胞白血病的靶向治疗是什么？",
    "免疫性血小板减少症的治疗原则是什么？",
    "肺癌的分型及治疗策略是什么？",
    "乳腺癌的内分泌治疗适应证是什么？",
    "结直肠癌的筛查方法有哪些？",
    "胃癌的手术方式如何选择？",
    "肝癌的介入治疗适应证是什么？",
    "急性阑尾炎的手术指征是什么？",
    "胆囊结石合并胆囊炎的处理原则是什么？",
    "急性肠梗阻的非手术治疗适应证是什么？",
    "腹股沟疝的手术修补方式有哪些？",
    "甲状腺癌的手术范围如何确定？",
    "烧伤面积的评估方法是什么？",
    "骨折的固定原则是什么？",
    "脊柱骨折的手术指征有哪些？",
    "膝关节骨性关节炎的阶梯治疗是什么？",
    "股骨头坏死的分期及治疗是什么？",
]

FOLLOWUPS = [
    "能更详细说明一下吗？",
    "你提到的内容中有没有遗漏的重要信息？",
    "谢谢，这个很有帮助！",
    "好的，明白了",
    "这个回答不够完整，请补充重要内容",
    "你能给出具体的剂量或数值吗？",
    "请补充临床实际操作中需要注意的细节",
    "有没有相关的指南推荐？",
]

SYSTEM = "你是一个专业的医学助手，请简洁准确地回答医学问题。"
MODEL  = "Qwen3.5-9B"
OPD_URL = f"http://localhost:{args.opd_port}"

# ─── 3. 发送对话（在线程里跑，不阻塞主线程）────────────────
def send_conversations():
    questions = QUESTIONS[:args.num]
    logger.info(f"开始发送 {len(questions)} 条对话...")
    ok = err = 0
    for i, q in enumerate(questions):
        sid = str(uuid.uuid4())
        try:
            msgs1 = [{"role":"system","content":SYSTEM},{"role":"user","content":q}]
            r1 = httpx.post(f"{OPD_URL}/v1/chat/completions",
                json={"model":MODEL,"messages":msgs1,"max_tokens":300,"temperature":0.7},
                headers={"X-Session-Id":sid,"X-Turn-Type":"main"}, timeout=90)
            r1.raise_for_status()
            reply = r1.json()["choices"][0]["message"]["content"] or ""

            fup = FOLLOWUPS[i % len(FOLLOWUPS)]
            msgs2 = msgs1 + [{"role":"assistant","content":reply},{"role":"user","content":fup}]
            r2 = httpx.post(f"{OPD_URL}/v1/chat/completions",
                json={"model":MODEL,"messages":msgs2,"max_tokens":200,"temperature":0.7},
                headers={"X-Session-Id":sid,"X-Turn-Type":"main","X-Session-Done":"true"}, timeout=90)
            r2.raise_for_status()
            ok += 1
            if (i+1) % 10 == 0:
                logger.info(f"  对话进度: {i+1}/{len(questions)}")
        except Exception as e:
            err += 1
            logger.warning(f"  第{i+1}条失败: {e}")
        time.sleep(0.3)
    logger.info(f"对话发送完成: 成功={ok} 失败={err}")

conv_thread = threading.Thread(target=send_conversations, daemon=True)
conv_thread.start()

# ─── 4. 等待收集够 batch_size 个 Sample ──────────────────────
logger.info(f"等待 {args.batch_size} 个 Sample（judge 评估需要时间）...")
samples_list = []
deadline = time.time() + 600  # 10分钟超时

while len(samples_list) < args.batch_size and time.time() < deadline:
    try:
        _, group = output_queue.get(timeout=5)
        samples_list.extend(group)
        logger.info(f"  Sample 进度: {len(samples_list)}/{args.batch_size}")
    except queue.Empty:
        if not conv_thread.is_alive() and output_queue.empty():
            logger.info("对话发送完成，等待剩余 judge 评估...")
            time.sleep(10)
            if output_queue.empty():
                break

logger.info(f"共收集 {len(samples_list)} 个 Sample，开始训练")
if not samples_list:
    logger.error("没有 Sample！退出")
    sys.exit(1)

# ─── 5. 加载模型（LoRA）──────────────────────────────────────
logger.info("加载模型 + LoRA...")
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)

# 4-bit 量化配置（QLoRA）：把模型显存从 ~53GB 降到 ~10GB
from transformers import BitsAndBytesConfig
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

# 检查是否有已有的 LoRA checkpoint（继续训练）
lora_path = f"{args.save_dir}/latest"
if os.path.exists(lora_path):
    from peft import PeftModel
    base = AutoModelForCausalLM.from_pretrained(MODEL_PATH,
                                                 quantization_config=bnb_config,
                                                 device_map="cuda", trust_remote_code=True)
    model = PeftModel.from_pretrained(base, lora_path)
    logger.info(f"加载已有 LoRA（4-bit）: {lora_path}")
else:
    base = AutoModelForCausalLM.from_pretrained(MODEL_PATH,
                                                 quantization_config=bnb_config,
                                                 device_map="cuda", trust_remote_code=True)
    from peft import prepare_model_for_kbit_training
    base = prepare_model_for_kbit_training(base)
    lora_cfg = LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj","v_proj"],
                           lora_dropout=0.05, bias="none", task_type="CAUSAL_LM")
    model = get_peft_model(base, lora_cfg)
    logger.info("新建 QLoRA（4-bit 量化）")

model.print_trainable_parameters()
model.train()

# ─── 6. 训练步骤 ─────────────────────────────────────────────
MAX_LEN   = 1024
optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

# 按 batch_size 分批训练
use_samples = samples_list[:args.batch_size]
losses = []

for step_idx in range(0, len(use_samples), args.batch_size):
    batch = use_samples[step_idx : step_idx + args.batch_size]
    optimizer.zero_grad()

    total_loss  = None
    token_count = 0

    for s in batch:
        ids      = list(s.tokens)[:MAX_LEN]
        resp_len = min(s.response_length, MAX_LEN)
        mask     = list(s.loss_mask)[:resp_len]
        slps     = list(s.rollout_log_probs)[:resp_len]
        tlps_raw = s.teacher_log_probs
        tlps     = (tlps_raw.tolist() if hasattr(tlps_raw, 'tolist') else list(tlps_raw))[:resp_len]

        id_t = torch.tensor([ids], dtype=torch.long).cuda()
        with torch.cuda.amp.autocast(dtype=torch.bfloat16):
            out    = model(input_ids=id_t)
            logits = out.logits[0]  # [T, V]

        prompt_len = len(ids) - resp_len
        for t, (m, slp, tlp) in enumerate(zip(mask, slps, tlps)):
            if m == 0:
                continue
            pos = prompt_len + t - 1
            if pos < 0 or pos >= logits.shape[0]:
                continue
            tok_id = ids[prompt_len + t] if (prompt_len + t) < len(ids) else 0
            student_lp = torch.nn.functional.log_softmax(logits[pos], dim=-1)[tok_id]
            teacher_lp = torch.tensor(float(tlp), device="cuda")
            step_loss  = -(teacher_lp - student_lp)  # KL: push student → teacher
            total_loss = step_loss if total_loss is None else total_loss + step_loss
            token_count += 1

    if total_loss is None or token_count == 0:
        logger.warning("本 batch 无有效 token，跳过")
        continue

    avg_loss = total_loss / token_count
    avg_loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    optimizer.step()

    loss_val = avg_loss.item()
    losses.append(loss_val)
    logger.info(f"  训练步骤 {len(losses)}: loss={loss_val:.4f}  tokens={token_count}")

# ─── 7. 保存 ─────────────────────────────────────────────────
os.makedirs(f"{args.save_dir}/latest", exist_ok=True)
os.makedirs(f"{args.save_dir}/step_{len(losses)}", exist_ok=True)
model.save_pretrained(f"{args.save_dir}/latest")
model.save_pretrained(f"{args.save_dir}/step_{len(losses)}")

# ─── 8. 汇总 ─────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"训练完成汇总")
print(f"  对话条数:    {args.num}")
print(f"  Sample 数:   {len(samples_list)}")
print(f"  训练步骤数:  {len(losses)}")
print(f"  Loss 列表:   {[f'{l:.4f}' for l in losses]}")
if len(losses) > 1:
    trend = "↓ 下降" if losses[-1] < losses[0] else "↑ 上升"
    print(f"  Loss 趋势:   {losses[0]:.4f} → {losses[-1]:.4f}  {trend}")
print(f"  LoRA 保存:   {args.save_dir}/latest")
print(f"{'='*60}")
print(f"\n下一步: python run_opd_train.py --num 100 --batch-size 32")
