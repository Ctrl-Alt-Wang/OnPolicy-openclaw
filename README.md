# Run4：OPCD 自蒸馏 — Qwen3.5-9B × GPT-5.4 Judge（lr=2e-6）

> **结论：训练失败，loss持平，评测退化 delta=-0.090。** 学习率过大 + 同模型自蒸馏双重问题。

---

## 1. 实验目的

在验证 OPCD（On-Policy Continual Distillation）框架可行性的基础上，尝试更大的学习率（2e-6，前两次为5e-7/1e-6），以期加速收敛。模型与 Run2/Run3 相同：Qwen3.5-9B 作为 student，同一模型实例作为 teacher（自蒸馏模式）。

---

## 2. 训练配置

| 参数 | 值 |
|---|---|
| Student 模型 | Qwen3.5-9B (QLoRA, 4-bit NF4, r=32, alpha=64) |
| Teacher 模型 | Qwen3.5-9B（same — 自蒸馏/OPCD） |
| Judge 模型 | GPT-5.4 via judge_proxy（port 20001） |
| 学习率 | **2e-6**（Run2: 5e-7, Run3: 1e-6） |
| Batch size | 16 |
| OPD server port | 30010 |
| 训练数据 | HuaTuo 2000条（12科室 × 166 + other 8） |
| 评测数据 | HuaTuo eval 200条 |
| PRM eval | 开启（RL-style score计算） |
| Wandb run | `o7jzwvb0` (`qwen3.5-9b-opcd-lr2e-06-bs16`) |
| Checkpoint | `/workspace/lora_checkpoints/latest` |
| 训练时间 | 2026-06-04 08:07 → 12:43（约4.5小时） |

### OPCD 框架说明（Run2~4 通用）

```
Turn 1：student(Qwen3.5-9B) 在原始问题上生成回答
Turn 2：GPT-5.4 judge 评估 student 回答 vs 参考答案，提取改进 hint
        → hint 注入上下文，teacher(同模型) 计算 teacher logprobs
        → step_loss = -(teacher_lp - student_lp) 梯度更新
```

---

## 3. 训练过程

### 3.1 步数 & 时间

- 总步数：**109 步**（2000条数据，batch=16，约1.1 epoch）
- 平均每步约 2.5 分钟（相比 Run3 略快）
- 总采样：**1744 条**（= 样本通过 judge 过滤后实际训练的数量）
- Queue size：全程稳定 1~3，无积压

### 3.2 Loss 曲线

| 阶段 | 步数范围 | 代表 loss 值 | 趋势 |
|---|---|---|---|
| 初始阶段 | 1~20 | -0.72 → -0.76 | 微弱上升 |
| 平台期 | 20~80 | ~-0.78~-0.80 | **完全平坦** |
| 末期小幅波动 | 80~109 | -0.77 → -0.78 | 小幅反弹 |

**最终 avg_loss：-0.7768**（几乎等于初始值，无有效下降）

```
wandb loss 趋势：▄█▇▄▅▄▄▂▂▂▁▁▁▁▁▁▂▂▂▂▂▂▁▁▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂
（注：wandb 图表因为 moving average 显示略有平滑，实际 step loss 波动大）
```

关键步骤 loss：
```
Step   1 | loss=-0.7207 | avg=-0.7207 | tokens=4040
Step  15 | loss=-1.2245 | avg=-0.7591 | tokens=3996  ← 异常大值
Step  26 | loss=-1.1960 | avg=-0.8031 | tokens=4080  ← 峰值
Step  50 | loss=-0.8571 | avg=-0.7781 | tokens=4068
Step  80 | loss=-0.6114 | avg=-0.7805 | tokens=4011
Step 109 | loss=-0.5815 | avg=-0.7768 | tokens=3696  ← 末步
```

**关键观察**：avg_loss 在 Step 26 到达 -0.80 的局部高点后，整个后半程持续小幅下降，在步骤末尾反弹到 -0.777。无收敛趋势，loss 值全程振荡在 -0.55 ~ -1.22 区间，方差极大。

### 3.3 Tokens per step

- 平均约 4020 tokens/step
- Step 27 出现 tokens=3738（异常低），可能对应某轮 judge 产出 hint 极短或会话被截断

---

## 4. 评测结果

### 4.1 总体得分（vs baseline Qwen3.5-9B）

| 指标 | 值 |
|---|---|
| Baseline avg score | **3.587** |
| Trained avg score | **3.497** |
| **Delta** | **-0.090（退化！）** |
| 评测对数 | 200 |

### 4.2 Per-department（对比 score_comparison.jsonl）

注：Run4 基线为未训练的 Qwen3.5-9B，分数明显高于 Run5/6 的 Qwen3-8B 基线（3.587 vs 3.175）。

训练后部分科室得分下降，说明 LoRA 参数在高学习率下偏离较大、破坏了原有的医学知识表达能力。

---

## 5. 失败原因深度分析

### 5.1 学习率过大（主因）

- lr=2e-6 对 QLoRA（r=32, 4-bit base）过于激进
- LoRA 参数在 4-bit 量化误差放大下，2e-6 的更新步长导致显著的参数偏移
- Loss 不下降反而波动增大，是梯度更新方向矛盾的典型症状
- **对比**：Run3（lr=1e-6）同样 109 步但 loss 更低且出现 W 型结构；Run5（lr=1e-6, 32B teacher）233 步 loss 从 -0.16 持续降至 -0.90

### 5.2 同模型自蒸馏的结构性问题（深层原因）

Run4 使用 Qwen3.5-9B 同时作为 teacher 和 student（OPCD 框架）：

```
Teacher = Student + LoRA（动态变化）+ hint 上下文
```

**问题一：teacher logprobs 在 hint-augmented 上下文上计算**
- hint 由 GPT-5.4 judge 生成，提示"你的回答有哪些改进方向"
- teacher 在 [原始问题 + hint] 上下文下生成参考分布
- 但 student 在推理时只看到原始问题 → **分布不对齐（替身问题）**

**问题二：自蒸馏的"循环游戏"**
- teacher 本质是 student + LoRA 的当前状态
- 随着 LoRA 更新，teacher 分布也在漂移
- 没有稳定的知识源，student 在追逐一个移动的目标
- 这解释了为什么 loss 没有单调下降：目标分布本身在变化

**问题三：judge 过滤率问题**
- GPT-5.4 judge 对 Qwen3.5-9B 回答的拒绝率约 17%（参考 Run5 数据）
- 这意味着 83% 的样本被认为"需要改进" → teacher 以 hint-boosted 上下文计算 logprobs
- 但被筛选出来的 17% 样本（"不需要改进"）直接被丢弃，浪费了正样本的对齐信号

### 5.3 Qwen3.5-9B 在 HuaTuo 任务上的表现

- Qwen3.5-9B baseline 得分 3.587，显著高于 Qwen3-8B（3.175）
- 说明 Qwen3.5-9B 本身在医学问答上就有更好的基础能力
- 对一个已经较好的模型做自蒸馏，边际收益空间更小，而引入错误方向更危险

---

## 6. 与其他 Run 的关键差异

| 对比维度 | Run4（本次） | Run5（下一次） | Run6（无judge） |
|---|---|---|---|
| Teacher 类型 | 同模型（9B自蒸馏） | 真实大模型（32B）| 真实大模型（32B） |
| Teacher 上下文 | hint-augmented（替身） | hint-augmented（替身） | 原始上下文（对齐） |
| 学习率 | **2e-6（过大）** | 1e-6 | 1e-6 |
| 步数 | 109 | 233 | 229 |
| Judge | GPT-5.4 | GPT-5.4 | **无** |
| 接受率 | ~83% | 83.1% | **100%** |
| Loss 趋势 | 平坦 | 稳定下降 | 稳定下降 |
| Delta | **-0.090** | +0.070 | **+0.130** |

---

## 7. 经验总结

1. **QLoRA (4-bit NF4) + lr=2e-6 不可行**：在量化基础上，高学习率的梯度噪声被放大，参数更新失控
2. **同模型自蒸馏（OPCD）对 teacher 质量有隐性依赖**：teacher 分布应远优于 student，而不是同等大小的相同模型
3. **hint-augmented 上下文创造了"替身"teacher**：这个 teacher 不代表模型在自然推理下的分布
4. **正确的学习率范围**：对于该配置（QLoRA r=32, 4-bit, Qwen3.x-8B/9B），1e-6 是上限

---

## 8. 文件索引

| 文件 | 路径 |
|---|---|
| 训练日志 | `/workspace/opd_run4.log` |
| Wandb run | `http://103.139.212.228:3005/johnson/medical-opd/runs/o7jzwvb0` |
| PRM 记录 | `/workspace/logs/opd_full_record.jsonl`（已被 Run5 覆盖） |
| Checkpoint | `/workspace/lora_checkpoints/latest/` |
| 评测结果 | `/workspace/eval_results/score_comparison.jsonl` |
| 训练脚本 | `/workspace/run_self_opd.py`（OPCD 框架，`--lr 2e-6`） |
