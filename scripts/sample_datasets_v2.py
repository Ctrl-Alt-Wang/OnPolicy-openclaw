"""
医学数据集采样脚本 v2（修复字段名）
HuatuoGPT 字段: data[0]=问题, data[1]=答案
CMB-Exam  字段: exam_type, exam_class, exam_subject, question, answer, option
"""
import os, json, random, re, collections
from pathlib import Path
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

random.seed(42)
OUTPUT_DIR = Path("/workspace/data")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from datasets import load_dataset

# ─── 科室关键词映射 ────────────────────────────────────────────
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

# ═══ Step 1: HuatuoGPT 训练集 ═══════════════════════════════
print("=" * 60)
print("Step 1: 下载 HuatuoGPT...")
ds = load_dataset("FreedomIntelligence/HuatuoGPT-sft-data-v1", split="train")
print(f"  总量: {len(ds)} 条，字段: {list(ds.features.keys())}")

# 解析并分桶
dept_buckets = collections.defaultdict(list)
for item in ds:
    raw = item["data"]
    # data 是 [问题, 答案] 两个元素的列表
    if not isinstance(raw, list) or len(raw) < 2:
        continue
    q = raw[0].replace("问：", "").replace("问:", "").strip()
    a = raw[1].replace("答：", "").replace("答:", "").strip()
    if len(q) < 10 or len(a) < 20:
        continue
    dept = classify_text(q + a)
    dept_buckets[dept].append({"instruction": q, "output": a, "dept": dept})

print("\n  科室分布（分类后）:")
for dept, items in sorted(dept_buckets.items(), key=lambda x: -len(x[1])):
    print(f"    {dept:12s}: {len(items):6,} 条")

# 分层采样 2000 条
TRAIN_N = 2000
DEPT_LIST = [d for d in DEPT_KEYWORDS.keys()]
per_dept = TRAIN_N // len(DEPT_LIST)

train_data = []
for dept in DEPT_LIST:
    bucket = dept_buckets.get(dept, [])
    n = min(per_dept, len(bucket))
    train_data.extend(random.sample(bucket, n))
    print(f"  采样 {dept}: {n} 条")

# 不足 2000 从"其他"补
shortfall = TRAIN_N - len(train_data)
if shortfall > 0:
    others = dept_buckets.get("其他", [])
    extra = random.sample(others, min(shortfall, len(others)))
    train_data.extend(extra)
    print(f"  其他补充: {len(extra)} 条")

random.shuffle(train_data)
print(f"\n  ✅ 训练集: {len(train_data)} 条")

dist = collections.Counter(d["dept"] for d in train_data)
print("  最终分布:")
for dept, cnt in sorted(dist.items(), key=lambda x: -x[1]):
    print(f"    {dept:12s}: {cnt:4d} ({cnt/len(train_data)*100:.1f}%)")

train_path = OUTPUT_DIR / "train_huatuo_2000.jsonl"
with open(train_path, "w", encoding="utf-8") as f:
    for item in train_data:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
print(f"  保存: {train_path}")

# ═══ Step 2: CMB-Exam 评测集 ════════════════════════════════
print()
print("=" * 60)
print("Step 2: 下载 CMB-Exam...")
cmb = load_dataset("FreedomIntelligence/CMB", "CMB-Exam", split="test")
print(f"  总量: {len(cmb)} 条，字段: {list(cmb.features.keys())}")
print(f"  示例: {json.dumps(dict(cmb[0]), ensure_ascii=False)[:300]}")

# 看 exam_subject 分布
subject_buckets = collections.defaultdict(list)
for item in cmb:
    subj    = item.get("exam_subject", "未知")
    etype   = item.get("exam_type", "")
    eclass  = item.get("exam_class", "")
    q       = item.get("question", "")
    ans     = item.get("answer", "")
    options = item.get("option", {})

    if not q or not ans:
        continue
    # 只取选择题
    if item.get("question_type", "") not in ["单选题", "多选题", ""]:
        continue

    subject_buckets[subj].append({
        "exam_type":    etype,
        "exam_class":   eclass,
        "exam_subject": subj,
        "question":     q,
        "options":      options if isinstance(options, dict) else {},
        "answer":       ans,
    })

print(f"\n  考试科目分布 (top 20):")
for subj, items in sorted(subject_buckets.items(), key=lambda x: -len(x[1]))[:20]:
    print(f"    {subj:15s}: {len(items):5,} 条")

# 按 exam_subject 比例采样 200 条
EVAL_N = 200
total_avail = sum(len(v) for v in subject_buckets.values())
eval_data = []

for subj, items in subject_buckets.items():
    quota = max(1, round(len(items) / total_avail * EVAL_N))
    n = min(quota, len(items))
    eval_data.extend(random.sample(items, n))

# 调整到精确 200 条
if len(eval_data) > EVAL_N:
    eval_data = random.sample(eval_data, EVAL_N)
elif len(eval_data) < EVAL_N:
    largest = max(subject_buckets, key=lambda s: len(subject_buckets[s]))
    used = set(id(x) for x in eval_data)
    extras = [x for x in subject_buckets[largest] if id(x) not in used]
    need = EVAL_N - len(eval_data)
    eval_data.extend(random.sample(extras, min(need, len(extras))))

random.shuffle(eval_data)
print(f"\n  ✅ 评测集: {len(eval_data)} 条")

eval_dist = collections.Counter(d["exam_subject"] for d in eval_data)
print("  最终科目分布:")
for subj, cnt in sorted(eval_dist.items(), key=lambda x: -x[1])[:15]:
    print(f"    {subj:15s}: {cnt:3d} ({cnt/len(eval_data)*100:.1f}%)")

eval_path = OUTPUT_DIR / "eval_cmb_200.jsonl"
with open(eval_path, "w", encoding="utf-8") as f:
    for item in eval_data:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
print(f"  保存: {eval_path}")

# ═══ Step 3: 元信息 ══════════════════════════════════════════
meta = {
    "train": {
        "file": str(train_path), "total": len(train_data),
        "source": "HuatuoGPT-sft-data-v1", "seed": 42,
        "dist": {k: v for k, v in dist.items()},
    },
    "eval": {
        "file": str(eval_path), "total": len(eval_data),
        "source": "CMB-Exam (official test split)", "seed": 42,
        "dist": {k: v for k, v in eval_dist.items()},
    }
}
with open(OUTPUT_DIR / "dataset_meta.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)

print()
print("=" * 60)
print("全部完成！")
print(f"  训练集: {train_path}  ({len(train_data)} 条)")
print(f"  评测集: {eval_path}  ({len(eval_data)} 条)")
print(f"  元信息: {OUTPUT_DIR / 'dataset_meta.json'}")
