# Run6：纯 OPD 无 Judge（Qwen3-32B teacher → Qwen3-8B student，lr=1e-6）

> **结论：训练最成功，delta=+0.130（Run5 的 1.86x），loss 最终下降最多。** 移除 GPT-5.4 judge，teacher 在原始上下文上计算 logprobs，解决了 Run5 的"替身问题"。

---

## 1. 实验目的

Run5 证明了真实大模型 teacher 的有效性，但 delta=+0.070 仍然有限。理论上，标准 OPD（On-Policy Distillation）不需要 judge 模型——teacher 直接在原始问题上提供 logprobs，student 最大化这个分布即可。

**核心假设**：GPT-5.4 judge 引入的 hint-augmented 上下文创造了一个人工的"替身 teacher"，使得 student 学习的目标偏离了真正的大模型知识分布。移除 judge → 恢复真实分布 → 更好的蒸馏效果。

---

## 2. 训练配置

| 参数 | 值 |
|---|---|
| Student 模型 | Qwen3-8B (QLoRA, 4-bit NF4, r=32, alpha=64, GPU0) |
| Teacher 模型 | Qwen3-32B (BF16, SGLang, GPU1, port 20000) |
| Judge 模型 | **无**（no-judge 模式） |
| 学习率 | 1e-6 |
| Batch size | 16 |
| OPD server port | **30011**（避免与 Run5 冲突） |
| 训练数据 | HuaTuo 2000条（12科室 × 166 + other 8） |
| 评测数据 | HuaTuo eval 200条 |
| PRM eval | **关闭**（OPENCLAW_EVAL_MODE=0） |
| Wandb run | `7y6x5hca` (`qwen3-32b-teacher-8b-student-nojudge-opd-lr1e-06-bs16`) |
| Checkpoint | `/workspace/lora_ckpt_qwen3_8b_nojudge/latest` |
| 训练开始 | 2026-06-08 06:53 |
| 训练完成 | 2026-06-09 02:26（约19.5小时） |

### No-Judge 实现方式

在 `openclaw_opd_api_server.py` 的 `_opd_evaluate` 函数中添加了 no-judge bypass：

```python
if self._no_judge:
    # 直接在原始上下文（无 hint）上计算 teacher logprobs
    norm_orig = _normalize_messages_for_template(turn_data["messages"])
    orig_prompt_text = tokenizer.apply_chat_template(
        norm_orig, tokenize=False, add_generation_prompt=True
    )
    orig_full_text = orig_prompt_text + turn_data["response_text"]
    orig_ids = tokenizer(orig_full_text)["input_ids"]
    teacher_log_probs = await self._compute_teacher_log_probs(orig_ids, response_len)
    # 接受所有样本（100% 接受率）
    return {"accepted": True, "teacher_log_probs": teacher_log_probs, "hint": ""}
```

`_compute_teacher_log_probs` 通过 judge_proxy (port 20001) 以 `return_logprob=True` 模式转发到 SGLang，teacher 计算的上下文是**纯原始问题**，无任何 hint 注入。

### 系统架构（vs Run5 的差异）

```
Run5（有judge）:
  Turn1: student 生成回答
  Turn2: GPT-5.4 [原始问题 + student回答] → hint
         → teacher在[原始问题 + hint]上计算logprobs  ← "替身"

Run6（无judge）:
  Turn1: student 生成回答
  Turn2: teacher在[原始问题]上直接计算logprobs  ← "真实"
         → 跳过 GPT-5.4 调用，100% 样本被接受
```

---

## 3. 训练过程

### 3.1 步数 & 时间

- 总步数：**229 步**（vs Run5 的 233 步，基本相同规模）
- 平均每步约 5.1 分钟（比 Run5 慢约 13%，因为每条样本都触发 teacher 推理，而 Run5 有 17% 被 judge 直接丢弃）
- 总采样：**3664 条**（vs Run5 的 3728，相近）
- Queue size：绝大多数步骤为 0 或 1（无积压，说明 teacher 推理是速率限制因素）

### 3.2 接受率

**100%**：所有 2000 条数据都被接受为训练样本，无过滤。

对比 Run5 的 83.1%：
- Run6 多利用了约 20% 的数据
- 特别是那些被 judge 认为"已经足够好"的样本（Run5 中被丢弃的 17%）——这些样本在 Run6 中提供了**正向对齐信号**（student 的输出与 teacher 已经接近，loss 接近 0，但提供了正向梯度方向）

### 3.3 Loss 曲线（稳定下降，幅度最大）

| 阶段 | 步数范围 | avg_loss | 趋势 |
|---|---|---|---|
| 初始 | 1~30 | -0.43 → -0.45 | 缓慢上升（适应期）|
| 稳定阶段 | 30~120 | -0.45 → -0.48 | 平稳缓降 |
| 加速阶段 | 120~190 | -0.48 → -0.57 | 加速下降 |
| 末期 | 190~229 | -0.57 → -0.63 | 持续下降 |

**最终 avg_loss：-0.6252**（Run5 末期 avg_loss 约 -0.39，Run6 大幅下降）

```
Step   1 | loss=-0.4338 | avg=-0.4338 | tokens=3808
Step  30 | loss=-0.4892 | avg=-0.4475 | tokens=4197
Step  80 | loss=-0.5458 | avg=-0.4632 | tokens=3779
Step 120 | loss=-0.4804 | avg=-0.4867 | tokens=4315
Step 150 | loss=-0.7802 | avg=-0.5136 | tokens=4144
Step 180 | loss=-0.8477 | avg=-0.5470 | tokens=4000
Step 200 | loss=-0.8575 | avg=-0.5750 | tokens=4087
Step 225 | loss=-1.0212 | avg=-0.6172 | tokens=4035  ← checkpoint_step
Step 229 | loss=-1.0769 | avg=-0.6252 | tokens=782   ← 末步（truncated）
```

**关键对比：初始 loss**
- Run5: -0.1611 → Run6: **-0.4338**（2.7倍差距）
- 这个差距揭示了真实的知识 KL 散度：Qwen3-32B 在原始问题上的分布与 Qwen3-8B 相差更大
- Run5 的 -0.1611 是 hint-augmented teacher 人为压缩了这个差距的结果

```
wandb avg_loss 趋势：████▇▇▇▇▇▇▇▇▇▇▇▇▇▇▇▆▆▆▆▅▅▅▅▅▄▄▃▃▃▃▂▂▂▁▁▁
（方向：块越大 = 绝对值越大 = loss 越负 = 模型越"接近" teacher）
```

### 3.4 PRM 记录样例

```json
{"session_id": "ee8bc245-...", "turn": 1, "accepted": true, "hint": "", "votes": [], "teacher_logprob_len": 289}
{"session_id": "eb339f15-...", "turn": 1, "accepted": true, "hint": "", "votes": [], "teacher_logprob_len": 602}
```

`hint: ""` 且 `votes: []` 确认无 judge 调用。`teacher_logprob_len` 对应 teacher 计算的 token 数量，与 student 回答长度一致。

---

## 4. 评测结果

### 4.1 总体得分

| 指标 | 值 |
|---|---|
| Baseline avg score（Qwen3-8B 未训练） | **3.194** |
| Trained avg score（Run6 checkpoint） | **3.324** |
| **Delta** | **+0.130** |
| 评测对数 | 200 |
| 评测模型 | GPT-5.4（准确性/完整性/清晰度，各1-5分，取均值） |

### 4.2 Per-department 详细结果（对比 Run5）

| 科室 | Baseline | Run6 | Run6 delta | Run5 delta | 趋势 |
|---|---|---|---|---|---|
| 内分泌代谢 | 3.19 | 3.42 | **+0.23** | +0.00 | ↑大幅提升 |
| 呼吸 | 3.36 | 3.21 | **-0.15** | +0.04 | ↓退化 |
| 外科骨科 | 3.23 | 3.60 | **+0.38** | +0.25 | ↑进一步提升 |
| 妇产儿科 | 3.10 | 3.27 | **+0.17** | +0.02 | ↑显著提升 |
| 心血管 | 3.10 | 3.21 | **+0.10** | +0.10 | → 持平 |
| 急诊重症 | 3.48 | 3.40 | **-0.08** | -0.12 | ↑退化减少 |
| 感染免疫 | 3.08 | 3.19 | **+0.10** | +0.08 | → 持平 |
| 检验影像 | 3.24 | 3.42 | **+0.18** | +0.11 | ↑提升加大 |
| 消化 | 3.38 | 3.40 | **+0.02** | -0.21 | ↑Run5退化问题已修复 |
| 神经 | 3.12 | 3.48 | **+0.35** | +0.27 | ↑进一步提升 |
| 肾脏泌尿 | 3.21 | 3.17 | **-0.04** | +0.17 | ↓小幅退化 |
| 药理用药 | 2.81 | 3.08 | **+0.27** | +0.11 | ↑大幅提升 |

**9/12 科室提升（vs Run5 的 8/12），Run5 最大退化科室（消化-0.21）在 Run6 中修复为+0.02**

---

## 5. 为什么 Run6 > Run5：完整机制分析

### 5.1 替身问题的解决

| 维度 | Run5（有judge） | Run6（无judge） |
|---|---|---|
| Teacher 上下文 | `[问题 + hint]` | `[问题]` |
| Teacher 分布 | `P(y | x + hint)` | `P(y | x)` ← 真实 |
| Student 推理上下文 | `[问题]` | `[问题]` ← 对齐！ |
| 训练目标 | 最大化 hint 辅助的分布 | 最大化真实 32B 分布 |
| 初始 KL 散度 | 小（-0.16，hint压缩了差距）| 大（-0.43，真实差距） |

Run6 让 student 学习的目标与推理时面对的情景完全一致。

### 5.2 数据效率提升

- Run5 有效训练样本：1662/2000 = **83.1%**
- Run6 有效训练样本：2000/2000 = **100%**
- 多出约 338 条训练样本，其中包含：
  - "judge 认为已经足够好"的样本 → 这些样本提供了**正向对齐信号**，告诉 student 某些输出已经接近 32B teacher
  - "judge API 超时/失败"的样本 → Run5 中直接丢弃，Run6 中保留

### 5.3 更大的 KL 散度 = 更多学习空间

- Run5 初始 loss -0.16 意味着 teacher（hint-augmented）和 student 从一开始就很接近
- Run6 初始 loss -0.43 意味着真正的知识差距更大，student 有更多东西可以从 teacher 学习
- 这解释了为什么 Run6 的 loss 最终能降到 -1.08，而 Run5 只降到 -0.90

### 5.4 正向样本的重要性

Run5 过滤掉所有 judge 认为"已经足够好"的样本，逻辑是"只纠正错误"。但这相当于剥夺了：
- 让 student 知道"这种输出风格是 32B 也会产生的"的信号
- 对已经准确的输出进行参数强化
- 跨科室平衡的训练分布（judge 可能对某些科室更严格）

---

## 6. 局限性与潜在改进方向

### 6.1 无法利用 judge 信息

No-judge 模式放弃了 GPT-5.4 的医学评估能力：
- 无法识别"安全但低质量"的回答（如信息不足但听起来合理）
- 无法在特别危险的错误上施加更大的惩罚
- 可能导致少数科室（如急诊重症、肾脏泌尿）轻微退化

**潜在方案**：selective no-judge — 只在 judge 确认"好回答"的样本上使用原始上下文，在"需要改进"的样本上使用适度 hint 辅助的上下文

### 6.2 训练时间较长

- 每条样本都需要 teacher 推理（无 judge 早停）→ 约 19.5 小时
- 优化空间：batch teacher inference，减少 teacher 推理次数

### 6.3 分布漂移仍存在

teacher 在固定的原始上下文上计算 logprobs，而 student 在训练中持续更新。随着 student 越来越接近 teacher，KL 散度减小，梯度信号自然减弱。这是 on-policy distillation 的内在特性，非本次实验独有问题。

---

## 7. 与其他 Run 完整对比

| 维度 | Run2 | Run3 | Run4 | Run5 | **Run6** |
|---|---|---|---|---|---|
| Student | 9B | 9B | 9B | 8B | **8B** |
| Teacher | 9B(self) | 9B(self) | 9B(self) | 32B | **32B** |
| LR | 5e-7 | 1e-6 | 2e-6 | 1e-6 | **1e-6** |
| Judge | 有 | 有 | 有 | 有 | **无** |
| Teacher 上下文 | hint+原始 | hint+原始 | hint+原始 | hint+原始 | **原始** |
| 接受率 | ~83% | ~83% | ~83% | 83.1% | **100%** |
| 步数 | 48 | 116 | 109 | 233 | **229** |
| 初始 loss | — | — | -0.72 | -0.16 | **-0.43** |
| 末步 loss | — | — | -0.58 | -0.90 | **-1.08** |
| Delta | N/A | N/A | -0.090 | +0.070 | **+0.130** |

---
<img width="2409" height="900" alt="image" src="https://github.com/user-attachments/assets/e0529599-9ec3-46b0-a9e3-de7592773952" />

## 8. 文件索引

| 文件 | 路径 |
|---|---|
| 训练日志 | `/workspace/logs/nojudge_train.log`（12MB） |
| Wandb run | `http://103.139.212.228:3005/johnson/medical-opd/runs/7y6x5hca` |
| PRM 记录 | `/workspace/logs/opd_nojudge_record_prm.jsonl`（268KB，2000条） |
| Checkpoint | `/workspace/lora_ckpt_qwen3_8b_nojudge/latest/` |
| 评测输出 | `/workspace/eval_results/trained_qwen3_8b_nojudge.jsonl` |
| 评测得分 | `/workspace/eval_results/score_comparison_nojudge.jsonl` |
| OPD server（修改版） | `/workspace/OnPolicy/OpenClaw-RL/openclaw-opd/openclaw_opd_api_server.py` |
| 训练脚本 | `/workspace/run_self_opd_32b_nojudge.py` |
| 评测脚本 | `/workspace/run_eval_qwen3_8b_nojudge.py` |
| 打分脚本 | `/workspace/run_score_nojudge.py` |
