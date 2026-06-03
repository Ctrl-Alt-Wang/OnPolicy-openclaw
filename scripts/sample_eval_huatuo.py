"""
从 HuatuoGPT 采样 200 条 hold-out 评测集
- 严格排除训练集中已有的题目（按 instruction 文本去重）
- 按科室分层：12 科室各约 16-17 条
- 保留参考答案用于 judge 评分
"""
import json, random, collections, os, hashlib
from pathlib import Path

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
random.seed(123)   # 和训练集用不同的种子

OUTPUT_DIR = Path("/workspace/data")

# ── 加载训练集，提取已用题目的指纹（防重叠）────────────────
print("=== 加载训练集（用于去重）===")
train_path = OUTPUT_DIR / "train_huatuo_2000.jsonl"
train_data = [json.loads(l) for l in open(train_path, encoding="utf-8")]

# 用 instruction 文本的 hash 做指纹，快速查重
def fingerprint(text):
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()

train_fps = set(fingerprint(d["instruction"]) for d in train_data)
print(f"训练集: {len(train_data)} 条，已建立去重指纹")

# ── 科室关键词（和训练集保持完全一致）─────────────────────────
DEPT_KEYWORDS = {
    "内分泌代谢": ["糖尿病", "胰岛素", "甲状腺", "甲亢", "甲减", "痛风", "尿酸",
                   "肾上腺", "垂体", "库欣", "骨质疏松", "HbA1c", "血糖", "胰腺"],
    "心血管":     ["高血压", "心衰", "心肌梗死", "心绞痛", "心房颤动", "心律失常",
                   "他汀", "冠心病", "动脉硬化", "主动脉", "瓣膜", "心包", "心脏"],
    "呼吸":       ["肺炎", "哮喘", "慢阻肺", "结核", "胸腔积液", "肺栓塞",
                   "呼吸衰竭", "支气管", "肺癌", "间质性肺", "气胸", "咳嗽"],
    "消化":       ["胃炎", "溃疡", "肝硬化", "胰腺炎", "结肠炎", "克罗恩",
                   "幽门螺旋杆菌", "消化道出血", "肝癌", "腹泻", "便秘", "胆囊"],
    "肾脏泌尿":   ["肾衰", "透析", "蛋白尿", "肌酐", "肾病综合征", "尿路感染",
                   "肾小球", "尿毒症", "造影剂", "肾功能", "CKD", "肾炎"],
    "神经":       ["脑卒中", "脑梗", "脑出血", "癫痫", "帕金森", "阿尔茨海默",
                   "重症肌无力", "颅内压", "脑膜炎", "脱髓鞘", "神经"],
    "感染免疫":   ["脓毒症", "感染", "抗生素", "免疫", "HIV", "乙肝", "丙肝",
                   "流感", "细菌", "病毒", "真菌", "狼疮", "类风湿", "炎症"],
    "外科骨科":   ["手术", "骨折", "阑尾炎", "腹股沟", "疝气", "外伤",
                   "烧伤", "关节炎", "脊柱", "股骨头", "膝关节", "骨科"],
    "妇产儿科":   ["妊娠", "产后", "乳腺", "子宫", "卵巢", "月经", "新生儿",
                   "儿童", "黄疸", "川崎", "手足口", "小儿", "产科"],
    "急诊重症":   ["ICU", "休克", "急救", "心肺复苏", "中毒", "过敏",
                   "DIC", "ARDS", "机械通气", "溶栓", "急诊", "急性"],
    "药理用药":   ["剂量", "禁忌", "不良反应", "相互作用", "用法", "药物",
                   "处方", "适应症", "副作用", "毒性", "用量", "给药"],
    "检验影像":   ["检查", "化验", "CT", "MRI", "超声", "心电图", "活检",
                   "穿刺", "内镜", "X线", "正常值", "参考值", "诊断"],
}

def classify_text(text):
    scores = {}
    for dept, kws in DEPT_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score > 0:
            scores[dept] = score
    return max(scores, key=scores.get) if scores else "其他"

# ── 遍历华佗数据集，排除训练集，分桶 ──────────────────────────
print("\n=== 遍历华佗数据集（排除训练集）===")
from datasets import load_dataset
ds = load_dataset("FreedomIntelligence/HuatuoGPT-sft-data-v1", split="train")
print(f"华佗总量: {len(ds)} 条")

dept_buckets = collections.defaultdict(list)
skipped = 0

for item in ds:
    raw = item["data"]
    if not isinstance(raw, list) or len(raw) < 2:
        continue
    q = raw[0].replace("问：", "").replace("问:", "").strip()
    a = raw[1].replace("答：", "").replace("答:", "").strip()
    if len(q) < 10 or len(a) < 20:
        continue

    # 去重：跳过训练集里有的题
    if fingerprint(q) in train_fps:
        skipped += 1
        continue

    dept = classify_text(q + a)
    if dept != "其他":
        dept_buckets[dept].append({
            "instruction": q,
            "output": a,
            "dept": dept,
        })

print(f"排除训练题: {skipped} 条（符合预期，约 2000 条）")
print("\n可用数据（排除训练集后）科室分布:")
for dept, items in sorted(dept_buckets.items(), key=lambda x: -len(x[1])):
    print(f"  {dept:12s}: {len(items):6,} 条")

# ── 分层采样 200 条 ──────────────────────────────────────────
EVAL_N = 200
DEPT_LIST = list(DEPT_KEYWORDS.keys())
per_dept = EVAL_N // len(DEPT_LIST)   # 每科 ~16 条

eval_data = []
for dept in DEPT_LIST:
    bucket = dept_buckets.get(dept, [])
    n = min(per_dept, len(bucket))
    sampled = random.sample(bucket, n)
    eval_data.extend(sampled)
    print(f"  采样 {dept}: {n} 条")

shortfall = EVAL_N - len(eval_data)
if shortfall > 0:
    # 从最大桶补充
    largest = max(dept_buckets, key=lambda d: len(dept_buckets[d]))
    used_fps = set(fingerprint(d["instruction"]) for d in eval_data)
    extras = [x for x in dept_buckets[largest] if fingerprint(x["instruction"]) not in used_fps]
    eval_data.extend(random.sample(extras, min(shortfall, len(extras))))

random.shuffle(eval_data)
print(f"\n最终评测集: {len(eval_data)} 条")

# ── 最终去重验证 ──────────────────────────────────────────────
eval_fps = set(fingerprint(d["instruction"]) for d in eval_data)
overlap = eval_fps & train_fps
print(f"与训练集重叠检查: {len(overlap)} 条重叠（应为 0）")
if overlap:
    print("  ⚠️  有重叠，请检查！")
else:
    print("  ✅ 无重叠")

# ── 科室分布 ────────────────────────────────────────────────
final_dist = collections.Counter(d["dept"] for d in eval_data)
print("\n最终科室分布:")
for dept, cnt in sorted(final_dist.items(), key=lambda x: -x[1]):
    pct = cnt / len(eval_data) * 100
    print(f"  {dept:12s}: {cnt:3d} ({pct:.1f}%)")

# ── 保存 ────────────────────────────────────────────────────
eval_path = OUTPUT_DIR / "eval_huatuo_200.jsonl"
with open(eval_path, "w", encoding="utf-8") as f:
    for item in eval_data:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

print(f"\n✅ 保存: {eval_path}")

# ── 抽查 3 条 ────────────────────────────────────────────────
print("\n=== 抽查 3 条 ===")
sample3 = random.sample(eval_data, 3)
for i, d in enumerate(sample3, 1):
    print(f"\n[{i}] 科室: {d['dept']}")
    print(f"    问题: {d['instruction'][:80]}...")
    print(f"    参考: {d['output'][:80]}...")

print("\n完成！")
