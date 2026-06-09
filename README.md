# Run5：OPD 跨模型蒸馏 + GPT-5.4 Judge（Qwen3-32B teacher → Qwen3-8B student，lr=1e-6）

> **结论：训练成功，loss 稳定下降，评测 delta=+0.070。** 首次引入真实大模型（32B）作为 teacher，带来明显收益；但 judge 产生的 hint-augmented 上下文造成了"替身问题"，限制了提升幅度。

---

## 1. 实验目的

从根本上解决 Run2~4 的同模型自蒸馏问题：引入真正的大模型 Qwen3-32B 作为 teacher，Qwen3-8B 作为 student。这是真正的 OPD（On-Policy Distillation）：student 向一个更强的知识源学习，而非追逐自身的镜像。

同时维持 GPT-5.4 judge 过滤机制，以期只在"回答质量不足"的样本上施加蒸馏，避免强化已经正确的输出。

---

## 2. 训练配置

| 参数 | 值 |
|---|---|
| Student 模型 | Qwen3-8B (QLoRA, 4-bit NF4, r=32, alpha=64, GPU0) |
| Teacher 模型 | **Qwen3-32B (BF16, SGLang, GPU1, port 20000)** |
| Judge 模型 | GPT-5.4 via judge_proxy (port 20001) |
| 学习率 | 1e-6 |
| Batch size | 16 |
| OPD server port | 30010 |
| 训练数据 | HuaTuo 2000条（12科室 × 166 + other 8） |
| 评测数据 | HuaTuo eval 200条 |
| PRM eval | 开启（eval_mode=1） |
| Wandb run | `x4fcd7qb` (`qwen3-32b-teacher-8b-student-opcd-lr1e-06-bs16`) |
| Checkpoint | `/workspace/lora_ckpt_qwen3_8b/latest` |
| 训练开始 | 2026-06-05 06:24 |
| 训练完成 | 2026-06-05（约18小时后） |

### 系统架构

```
GPU0: Qwen3-8B (QLoRA, student, 训练中)
GPU1: Qwen3-32B (SGLang server, port 20000, teacher 推理)

judge_proxy (port 20001) — 双路由器:
  ├── return_logprob=True  → 转发至 SGLang(port 20000) → teacher logprobs
  └── return_logprob=False → 调用 GPT-5.4 API → judge 评估

OPD Server (port 30010):
  Turn1: student 在原始问题上生成回答
  Turn2: judge 评估 → 提取 hint → [原始问题 + hint] 上下文 → teacher 计算 logprobs
  → step_loss = -(teacher_lp - student_lp) → 梯度更新
```

---

## 3. 训练过程

### 3.1 步数 & 时间

- 总步数：**233 步**（2000条数据，batch=16）
- 平均每步约 4.5 分钟（比 Run4 慢，因为 32B teacher 推理更慢）
- 总采样：**3728 条**（1.86x 数据利用率，数据集循环了约两遍）
- 最终 checkpoint step：233

### 3.2 Judge 接受率统计

| 分位 | 接受数/总数 | 接受率 |
|---|---|---|
| Q1（前25%，1-500条） | 430/500 | **86.0%** |
| Q2（26-50%，501-1000条） | 404/500 | **80.8%** |
| Q3（51-75%，1001-1500条） | 416/500 | **83.2%** |
| Q4（后25%，1501-2000条） | 412/500 | **82.4%** |
| **总体** | **1662/2000** | **83.1%** |

**观察**：
- 约 16.9% 的样本被 judge 判定"已经足够好"或"judge 调用超时/失败"而丢弃
- 接受率随训练进行略有下降（86% → 82%），可能因为 student 能力提升后更多样本被判定为无需改进
- judge 失败（votes=[-1,-1,-1]）的样本在 Q1 初期较集中（judge_proxy 刚启动的预热期）

### 3.3 Loss 曲线（稳定下降）

| 阶段 | 步数范围 | avg_loss | 趋势 |
|---|---|---|---|
| 初始 | 1~20 | -0.16 → -0.29 | 快速下降 |
| 中期 | 20~100 | -0.29 → -0.37 | 稳定下降 |
| 后期 | 100~180 | -0.37 → -0.55 | 加速下降 |
| 末期 | 180~233 | -0.55 → -0.90 | 持续下降 |

**最终 avg_loss：-0.394**（相比 Run4 的 -0.777 低，因为起点不同）

关键步骤 loss：
```
Step   1 | loss=-0.1611 | avg=-0.1611  ← 起步极低
Step  50 | loss=-0.2415 | avg=-0.2415
Step 100 | loss=-0.2529 | avg=-0.2529
Step 150 | loss=-0.4497 | avg=-0.4497
Step 200 | loss=-0.7117 | avg=-0.6466
Step 233 | loss=-0.8980 | avg=-0.3938  ← 末步
```

**重要发现**：Step 1 的 loss 仅为 -0.1611，显著低于 Run6 的起始值 -0.4338。这不是因为模型表现更好，而是因为 hint-augmented 上下文使得 student 和 teacher 的分布差距**人为缩小**了——teacher 是在"回答应该如何改进"的提示下计算的，这个提示同时也修正了 student 生成的内容，导致 KL 散度初始就较低。

```
wandb avg_loss 趋势：▁▁▁▁▁▁▁▁▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▃▃▃▃▄▄▄▅▅▅▅▅▅▆▇█
（注：wandb 图表 y 轴方向：块越大 = loss 绝对值越大 = loss 越负）
```

---

## 4. 评测结果

### 4.1 总体得分

| 指标 | 值 |
|---|---|
| Baseline avg score（Qwen3-8B 未训练） | **3.175** |
| Trained avg score（Run5 checkpoint） | **3.245** |
| **Delta** | **+0.070** |
| 评测对数 | 200 |
| 评测模型 | GPT-5.4（准确性/完整性/清晰度，各1-5分，取均值） |

### 4.2 Per-department 详细结果

| 科室 | Baseline | Trained | Delta | 分析 |
|---|---|---|---|---|
| 内分泌代谢 | 3.27 | 3.27 | +0.00 | 无变化 |
| 呼吸 | 3.29 | 3.33 | **+0.04** | 微弱提升 |
| 外科骨科 | 3.23 | 3.48 | **+0.25** | 显著提升 |
| 妇产儿科 | 3.13 | 3.15 | +0.02 | 微弱提升 |
| 心血管 | 3.08 | 3.19 | **+0.10** | 提升 |
| 急诊重症 | 3.33 | 3.21 | **-0.12** | 退化（强基线 → 难提升） |
| 感染免疫 | 3.12 | 3.21 | **+0.08** | 提升 |
| 检验影像 | 3.25 | 3.36 | **+0.11** | 提升 |
| 消化 | 3.35 | 3.15 | **-0.21** | 明显退化 |
| 神经 | 3.04 | 3.31 | **+0.27** | 显著提升 |
| 肾脏泌尿 | 3.15 | 3.31 | **+0.17** | 提升 |
| 药理用药 | 2.81 | 2.92 | **+0.11** | 提升（基线最低） |

**8/12 科室提升，2/12 退化（消化-0.21、急诊-0.12），2/12 持平**

---

## 5. 替身问题（"替身 teacher"）分析

> 这是 Run5 最核心的设计缺陷，也是 Run6 要解决的问题。

### 5.1 什么是替身问题？

在 Run5 的 OPCD 框架中，teacher logprobs 不是在原始问题上计算的，而是在 **[原始问题 + hint]** 的 augmented 上下文上计算的：

```
原始上下文：
  System: "你是专业医学助手"
  User:   "请问糖尿病二型如何治疗？"
  
hint-augmented 上下文（teacher 使用的）：
  System: "你是专业医学助手"
  User:   "请问糖尿病二型如何治疗？"
  Hint:   "你的回答遗漏了生活方式干预，应该补充饮食控制和运动疗法..."
  
student 推理时使用的上下文：
  System: "你是专业医学助手"
  User:   "请问糖尿病二型如何治疗？"   ← 只有原始问题
```

### 5.2 为什么这造成了分布漂移？

- teacher 在 hint 指导下生成 logprobs，这个分布 `P_teacher(y | x + hint)` 不等于 teacher 在原始问题上的自然分布 `P_teacher(y | x)`
- student 被要求最大化 `P_teacher(y | x + hint)`，但推理时 `x + hint` 不存在
- **结果**：student 学到的是"在 hint 指导下如何写好答案"，而非"32B 模型自然地如何回答医学问题"
- 这个 hint-augmented teacher 是真实 teacher 的"替身"——看起来像 teacher，实际上是一个被 hint 操控的影子

### 5.3 量化证据

- Run5 初始 loss: **-0.16**（极低 → KL 散度小 → teacher 和 student 分布本就接近）
- Run6 初始 loss: **-0.43**（更高 → 真实的 32B 原始分布离 8B 更远 → 才是真正的知识差距）
- Run5 最终 delta: **+0.070** vs Run6: **+0.130**（相同配置，仅移除 hint，提升近翻倍）

---

## 6. 与其他 Run 对比

| 维度 | Run2 | Run3 | Run4 | **Run5** | Run6 |
|---|---|---|---|---|---|
| Student | Qwen3.5-9B | Qwen3.5-9B | Qwen3.5-9B | **Qwen3-8B** | Qwen3-8B |
| Teacher | 9B(self) | 9B(self) | 9B(self) | **32B(真实)** | 32B(真实) |
| LR | 5e-7 | 1e-6 | 2e-6 | **1e-6** | 1e-6 |
| Judge | GPT-5.4 | GPT-5.4 | GPT-5.4 | **GPT-5.4** | **无** |
| Teacher 上下文 | hint+原始 | hint+原始 | hint+原始 | **hint+原始（替身）** | **原始（真实）** |
| 接受率 | ~83% | ~83% | ~83% | **83.1%** | **100%** |
| 总步数 | 48 | 116 | 109 | **233** | 229 |
| 初始 loss | — | — | -0.72 | **-0.16** | -0.43 |
| 末步 loss | — | — | -0.58 | **-0.90** | -1.08 |
| Delta | N/A | N/A | -0.090 | **+0.070** | **+0.130** |

---

## 7. 经验与洞察

1. **真实大模型 teacher 至关重要**：从 Qwen3.5-9B 自蒸馏（Run4, delta=-0.090）切换到 Qwen3-32B 真正 OPD（Run5, delta=+0.070），证明 teacher 质量是核心变量
2. **hint-augmented 上下文是局限性**：GPT-5.4 judge 产生的 hint 虽然改善了 teacher 的"参考分布"，但同时破坏了 teacher-student 的上下文对齐
3. **Loss 起始值是诊断工具**：Run5 初始 loss -0.16 揭示了替身问题；Run6 初始 loss -0.43 才是真实的知识差距
4. **消化科退化的假设**：消化科的 baseline 分较高（3.35），说明 8B 模型在该领域已经较好，judge 产生的 hint 可能引入了错误方向的"改进"

---

## 8. 文件索引

| 文件 | 路径 |
|---|---|
| 训练日志 | `/workspace/logs/run_qwen3_32b_teacher.log`（13MB） |
| Wandb run | `http://103.139.212.228:3005/johnson/medical-opd/runs/x4fcd7qb` |
| PRM 记录 | `/workspace/logs/opd_full_record_prm.jsonl`（4.9MB，2000条） |
| Checkpoint | `/workspace/lora_ckpt_qwen3_8b/latest/` |
| 评测输出 | `/workspace/eval_results/trained_qwen3_8b.jsonl` |
| 评测得分 | `/workspace/eval_results/score_comparison_qwen3_8b.jsonl` |
| 评测日志 | `/workspace/logs/score_qwen3_8b.log` |
| 训练脚本 | `/workspace/run_self_opd_32b.py` |
