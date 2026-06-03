# Run 2 完整分析报告：OPSD + GPT-5.4 外部 Judge

> **分支**：`run2-gpt-judge-analysis`
> **训练时间**：2026-06-03 01:53 → 06:44（约 5 小时）
> **服务器**：117.50.216.160，A800 80GB

---

## 一、本次改动的核心：为什么引入外部 Judge？

### Run 1 的局限性

Run 1（OPSD 纯自蒸馏）中，judge 和 teacher 都是同一个 Qwen3.5-9B：

```
judge(Qwen3.5-9B): 看 student 回答 → 生成 hint
teacher(Qwen3.5-9B + hint): 重新算 logprobs
```

这产生了一个根本性的天花板问题：**模型用自己的认知来评判自己**。对于它本来就不懂的医学知识（如感染免疫、心血管的细节），它既无法生成准确的 hint，也无法真正"领先"自己。这解释了为什么 Run 1 在感染免疫（-0.23）和心血管（-0.17）科室出现了明显下降。

### Run 2 的设计思路

将 judge 替换为 GPT-5.4，保留本地模型作为 teacher：

```
judge(GPT-5.4 API): 看 student 回答 → 生成更高质量的 hint
teacher(Qwen3.5-9B + hint): 重新算 logprobs（logprobs 仍来自本地）
```

**核心理由**：
1. GPT-5.4 具备更广博的医学知识，对 student 回答的评判更准确
2. teacher 只需要提供 logprobs，不需要额外的医学知识，本地模型完全胜任
3. 闭源模型无法提供 logprobs，所以 teacher 永远只能是本地模型——这不是 OPD 而是 OPSD，见[术语澄清](#术语澄清)

---

## 二、术语澄清

| 术语 | 定义 | 本次是否符合 |
|------|------|------------|
| **OPD**（Online Policy Distillation）| teacher ≠ student，teacher 提供 logprobs | ❌ 本次 teacher = Qwen3.5-9B（同 student）|
| **OPSD**（Online Policy Self-Distillation）| teacher = student + hint augmentation | ✅ Run 1 和 Run 2 都是 OPSD |
| **OPCD**（On-Policy Continual Distillation）| OPSD 的学术论文名（arXiv 2602.12275）| ✅ 同上 |
| **OPSD + 外部 judge** | OPSD 中将 judge 换成外部更强模型 | ✅ Run 2 的准确描述 |

> **关键约束**：真正的 OPD 要求 teacher 是更强的外部模型（提供 logprobs），闭源模型（GPT-4/Claude）因为：① 没有 logprob API；② tokenizer 不一致——无法作为 teacher。即使有 logprob API，tokenizer 不同时 teacher 收到的 student token ID 会被映射到错误的词，logprob 完全无效。

---

## 三、技术实现：Judge Proxy 代理服务器

### 问题

OpenClaw-OPD 的 `_prm_url` 同时服务于两类请求：
- `return_logprob=False`：judge/eval 调用（只需文本生成）
- `return_logprob=True`：teacher logprob 计算（需要 SGLang `/generate` 端点）

两类调用用同一个 URL，无法直接替换成 GPT-5.4 API（格式不兼容）。

### 解决方案：judge_proxy.py（port 20001）

```
请求 → judge_proxy:20001
           │
           ├── return_logprob=False → GPT-5.4 API（http://8.219.115.209:6600）
           │        清理 Qwen special tokens → 发送为 user message → 返回文本
           │
           └── return_logprob=True  → SGLang:20000（本地 Qwen3.5-9B）
                    原样转发，获取 logprobs
```

**关键实现细节**：
1. GPT-5.4 使用 `max_completion_tokens`（不是 `max_tokens`，否则返回 400）
2. Qwen 的 chat template special tokens（`<|im_start|>` 等）需要用正则清理后再发给 GPT
3. 代理是异步的（FastAPI + httpx AsyncClient），不阻塞并发请求

**修改点**：`OPDArgs.prm_router_port = 20001`（从 20000 改为 20001）

```python
# scripts/run_self_opd.py 中的变化
class OPDArgs:
    ...
    prm_router_port = 20001  # Run 1: 20000（直接 SGLang）
                              # Run 2: 20001（通过 judge_proxy）
```

---

## 四、完整训练配置

### 环境配置

| 项目 | 配置 |
|------|------|
| 服务器 | A800 80GB × 1，117.50.216.160，SSH port 23 |
| Python 环境 | `/usr/local/miniconda3/envs/py312`（Python 3.12）|
| SGLang | 0.5.12.post1，port 20000，`--mem-fraction-static 0.3` |
| judge_proxy | FastAPI + uvicorn，port 20001 |
| OPD Server | openclaw-opd，port 30010 |
| GPU 分配 | SGLang ~25 GB + 训练模型 ~47 GB = 72 GB（满载但未 OOM）|

### 模型配置

| 项目 | 配置 |
|------|------|
| 基础模型 | Qwen3.5-9B（`/workspace/Qwen3.5-9B`）|
| 量化 | 4-bit NF4（bitsandbytes），double quant，compute dtype=bfloat16 |
| LoRA rank | r=16，alpha=32，dropout=0.05 |
| LoRA 目标层 | q_proj, k_proj, v_proj, o_proj（仅 attention，不含 Mamba 层）|
| 可训练参数 | 2,228,224 / 8,956,031,488（**0.025%**）|

### 训练超参数

| 参数 | 值 | 备注 |
|------|-----|------|
| `lr` | **5e-7** | 与 Run 1 相同，未改变 |
| `batch_size` | **16** | 未改变 |
| `MAX_LEN` | **256** | 截断序列长度（防 Mamba OOM）|
| `save_every` | 5 | 每 5 步保存 checkpoint |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | 防内存碎片 OOM |

### OPD Server 配置

| 参数 | 值 | 备注 |
|------|-----|------|
| `prm_m` | 3 | Judge 投票次数（多数票）|
| `prm_temperature` | 0.7 | Judge 生成温度 |
| `prm_max_new_tokens` | 1024 | Judge 最大输出长度 |
| `prm_router_port` | **20001** | ← Run 2 关键改动，指向 judge_proxy |

### Judge（GPT-5.4）配置

| 参数 | 值 |
|------|-----|
| API URL | `http://8.219.115.209:6600/v1/chat/completions` |
| Model | `gpt-5.4` |
| `max_completion_tokens` | 1024 |
| temperature | 0.7 |
| 调用次数 | 每条对话 3 次（prm_m=3 投票）|

### 训练数据

| 数据集 | 路径 | 条数 | 说明 |
|--------|------|------|------|
| 训练集 | `/workspace/data/train_huatuo_2000.jsonl` | 2000 | HuatuoGPT，12 科室各 166 条，seed=42 |
| 评测集 | `/workspace/data/eval_huatuo_200.jsonl` | 200 | 同源 hold-out，0 重叠，seed=123 |

**对话结构**：
```
Turn 1 → OPD Server（X-Turn-Type: main）：
  [system: "你是专业医学助手", user: <instruction>]
  → student 生成回答，OPD 记录 logprobs

Turn 2 → OPD Server（X-Turn-Type: main, X-Session-Done: true）：
  [..., assistant: <student_reply>, user: "参考一个更优秀的回答：<ref[:300]>"]
  → 参考答案前 300 字作为 next_state
  → GPT-5.4 judge 评判 student 回答 vs 参考答案，提取 hint
  → teacher（Qwen3.5-9B + hint）重新计算 logprobs
  → 产生 training sample，推入 output_queue
```

---

## 五、训练结果统计

| 指标 | 数值 |
|------|------|
| 总步数 | **110 步** |
| 总样本数 | **1760** |
| 接受率 | **88%**（1760 / 2000）|
| 训练时长 | 约 **5 小时** |
| 每步耗时 | 约 **2.7 分钟** |
| 最终 avg_loss | **-0.750** |
| WandB run | `qwen3.5-9b-opcd-lr5e-07-bs16`（第 2 条 run）|

---

## 六、训练曲线深度分析

### Loss 曲线（每步）

```
波动范围：-0.55 ~ -1.2
平均值：  约 -0.80
```

每步 loss 波动大是正常的，因为每个 batch 随机包含不同科室的问题，难度差异天然存在。不应从单步 loss 判断训练质量。

### avg_loss 曲线（累计均值）

```
起点（step 1）：-0.690
最低点（step ~30）：-0.750
终点（step 110）：-0.750（基本持平，没有回升）
```

**与 Run 1 的关键对比**：

| | Run 1（OPSD 自身 judge）| Run 2（OPSD + GPT-5.4 judge）|
|--|--|--|
| 起点 | -0.760 | -0.690 |
| 最低点 | -0.860（step ~30）| -0.750（step ~30）|
| 终点 | -0.840（**有回升**）| -0.750（**无回升**）|
| U 形完整度 | 右侧初现（+0.02 回升）| 右侧未出现 |
| 总幅度（最低-起点）| -0.10 | -0.06 |

### avg_loss 含义解读

```
avg_loss 更负 → teacher 与 student 的分布差距扩大
               → student 被 teacher 推向新方向，还没学会

avg_loss 回升 → teacher 与 student 的分布差距收窄  
               → student 开始追上 teacher，模型在收敛

U形完整 = 先被推（左侧下降）+ 再追上（右侧回升）
        = 完整的"探索 → 收敛"周期
```

**Run 2 无 U 形右侧的原因**：

1. **GPT-5.4 的 hint 质量更高** → teacher 在 hint 帮助下"领先"幅度更大 → 同样 lr=5e-7 的梯度更新追不上
2. **110 步不够** → 即使 lr 够，右侧回升可能需要 step 150+ 才出现
3. **两个因素叠加** → 在 110 步内既没有 lr 够快，也没有步数够多

---

## 七、评测结果分析

### 推理方式说明

由于合并了 QLoRA 后的模型无法被 SGLang 加载（`Qwen3_5ForCausalLM` 架构不被支持），两轮均采用 **transformers 4-bit 直接推理**，确保 baseline 和 trained 使用完全相同的推理路径。

### 三轮完整对比

| 科室 | Baseline | Run 1（OPSD）| Run 2（OPSD+GPT）| Run1→Run2 变化 |
|------|---------|------------|-----------------|--------------|
| 药理用药 | 3.56 | +0.08 ✅ | **+0.15 ✅** | ↑ 外部 judge 在药理上更精准 |
| 肾脏泌尿 | 3.40-3.44 | **+0.25 ✅** | +0.11 ✅ | ↓ 但仍有提升 |
| 神经 | 3.54-3.69 | +0.04 | **+0.08 ✅** | ↑ |
| 外科骨科 | 3.40-3.44 | -0.04 | **+0.04 ✅** | ↑ 扭负为正 |
| 检验影像 | 3.56-3.64 | -0.15 | -0.06 | ↑ 下降幅度减小 |
| 消化 | 3.56-3.63 | -0.06 | -0.12 | ↓ |
| 内分泌代谢 | 3.60 | -0.12 | -0.06 | ↑ 下降幅度减小 |
| 呼吸 | 3.60-3.65 | **+0.06 ✅** | -0.17 ⬇️ | ↓ 下降，异常 |
| 心血管 | 3.44-3.48 | -0.17 | -0.21 | ↓ |
| 急诊重症 | 3.58 | -0.29 | -0.21 | ↑ 下降幅度减小 |
| 感染免疫 | 3.75-3.77 | -0.23 | -0.17 | ↑ 下降幅度减小 |
| 妇产儿科 | 3.50-3.54 | -0.13 | -0.23 ⬇️ | ↓ 下降更多，异常 |
| **总体 delta** | — | **-0.053** | **-0.070** | Run 2 略差 |

### 结果解读

**Run 2 总体略差（-0.070 vs -0.053）的原因**：
- 模型尚未收敛（avg_loss 没有出现 U 形右侧），处于"被 teacher 推走但还没追上"的过渡状态
- 此时评测的实际上是一个"半路上"的模型，不代表 GPT judge 方案的真实上限

**GPT-5.4 judge 的有效性证据**：
- 药理用药：+0.15 vs +0.08，显著更好。GPT-5.4 对具体药物剂量、禁忌症的评判更准确，hint 质量更高
- 外科骨科：从 -0.04 扭转为 +0.04。自身 judge 对外科操作细节的评判有限，GPT-5.4 更好
- 感染免疫、急诊重症：下降幅度均有所收窄，说明 GPT hint 质量有改善

**异常项目**：
- 呼吸：Run 1 +0.06 → Run 2 -0.17，明显变差。可能是 GPT-5.4 的 hint 改变了模型在呼吸科问题上的回答风格，但方向偏了
- 妇产儿科：Run 1 -0.13 → Run 2 -0.23，下降更多。类似原因，训练还在"被推"阶段，尚未收敛

---

## 八、Run 3 超参数决策推导

### 核心问题

在数据量固定（2000 条 → 约 110 步）的约束下，如何让 student 在 110 步内完成 U 形收敛？

### 定量分析

已知信息：
```
Run 1（自身 judge，lr=5e-7）：
  U 形转折点在 step ~30
  
Run 2（GPT-5.4 judge，lr=5e-7）：
  110 步无转折，说明转折点 > 110 步

估算：GPT judge 的 teacher-student gap 是自身 judge 的 N 倍
      Run 1 转折在 step 30 → Run 2 转折大约在 step 30 × N
      由于 110 步未见转折，N > 110/30 ≈ 3.7
      保守估计 N ≈ 4，转折点大约在 step 120

要在 110 步内出现转折，需要 lr 提升约 N 倍：
  lr_new = 5e-7 × 4 = 2e-6（激进）
  lr_new = 5e-7 × 2 = 1e-6（保守，预期转折在 step ~60）
```

### 决策：折中方案 lr=1e-6

| 选项 | lr | 预期转折 | 风险 | 选择 |
|------|-----|---------|------|------|
| 激进 | 2e-6 | step ~30 | loss 不稳定，可能过拟合 | |
| **折中** | **1e-6** | **step ~60** | 中等风险，有缓冲空间 | ✅ |
| 保守 | 5e-7 + batch=8 | step ~60（220步走完）| 训练时间翻倍 | |

**选择 lr=1e-6 的理由**：
1. 只改一个参数，其他变量不变，结果可解释性强
2. 2 倍 lr 不至于引起训练崩溃（QLoRA 本身有很强的正则化）
3. 预期在 step 50-70 出现 U 形转折，110 步内有 40-60 步的收敛时间

---

## 九、Run 1 vs Run 2 vs 计划 Run 3 配置对比

| 配置项 | Run 1 | Run 2 | **Run 3（计划）** |
|--------|-------|-------|-----------------|
| Judge | Qwen3.5-9B（自身）| GPT-5.4 | GPT-5.4（保持）|
| Teacher | Qwen3.5-9B | Qwen3.5-9B | Qwen3.5-9B（保持）|
| lr | 5e-7 | 5e-7 | **1e-6** ← 唯一改动 |
| batch_size | 16 | 16 | 16（不变）|
| MAX_LEN | 256 | 256 | 256（不变）|
| 训练数据 | 2000 条 | 2000 条 | 2000 条（不变）|
| prm_router_port | 20000 | 20001 | 20001（保持）|
| 预期步数 | ~110 | ~110 | ~110 |
| 预期 U 形转折 | step ~30 | 未出现 | step ~50-60 |

---

## 十、经验总结

1. **OPSD 中 judge 质量 ≠ 收敛速度**：更好的 judge 产生更大的 teacher-student gap，反而需要更高的 lr 才能在同等步数内收敛

2. **avg_loss 的 U 形是收敛指标**：右侧回升才是"student 真正在学"的信号，左侧下降只是"被推开"，不能混淆

3. **评测时机很重要**：未收敛时评测会低估方案的真实效果，应该在 U 形出现并稳定后再做 eval

4. **tokenizer 一致性是 OPSD/OPD 的硬约束**：teacher 接收的是 student 生成的 token ID，不同 tokenizer 会导致 ID 映射到错误的词，logprob 完全无效。真正的 OPD（teacher ≠ student）需要同系列开源模型，不能用闭源模型做 teacher

5. **GPT judge 代理方案有效**：利用 OpenClaw-OPD 中 `return_logprob` 字段区分 judge/teacher 调用，通过代理服务器实现路由，无需修改框架源码



<img width="2445" height="807" alt="image" src="https://github.com/user-attachments/assets/76dce535-11a5-4306-ac4e-7091abacf8ba" />

