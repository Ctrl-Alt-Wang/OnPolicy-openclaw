# 医学 Agent 在线策略蒸馏（OPSD / OPCD / OPD）实验记录

> **项目目标**：将线上医学 Agent（nanobot）接入 OpenClaw-RL 框架，通过在线策略蒸馏（OPD）实时训练本地医学语言模型，提升问答质量。
>
> **当前最佳结果**（Run6，2026-06-09）：Qwen3-32B teacher → Qwen3-8B student，无 judge，delta **+0.130**（相比 Run1 的 -0.053 提升了 0.183 分）
>
> **术语说明**：
> - **OPD**（Online Policy Distillation，在线策略蒸馏）：框架名称，通用概念
> - **OPSD**（Online Policy **Self**-Distillation，在线策略**自**蒸馏）：teacher = student（同模型自蒸馏）
> - **OPCD**（On-Policy Continual Distillation）：论文（arXiv 2602.12275）中对 OPSD 这类方法的学术称呼
> - **纯 OPD**：teacher 为真正的大模型（Qwen3-32B），student 为小模型（Qwen3-8B），无 judge 过滤

---

## Run 历史总览

| Run | 分支 | Student | Teacher | Judge | LR | 步数 | 接受率 | 初始Loss | 末步Loss | **Delta** |
|---|---|---|---|---|---|---|---|---|---|---|
| Run1 | master (原) | Qwen3.5-9B | 9B(self) | 9B(self) | 5e-7 | 110 | 88% | -0.78 | -0.80 | -0.053 |
| Run2 | run2-gpt-judge-analysis | Qwen3.5-9B | 9B(self) | GPT-5.4 | 5e-7 | 48 | ~83% | — | — | N/A |
| Run3 | run3 | Qwen3.5-9B | 9B(self) | GPT-5.4 | 1e-6 | 116 | ~83% | — | — | N/A |
| Run4 | **run4** | Qwen3.5-9B | 9B(self) | GPT-5.4 | **2e-6** | 109 | ~83% | -0.72 | -0.58 | **-0.090** |
| Run5 | **run5-opcd** | Qwen3-8B | **32B(真实)** | GPT-5.4 | 1e-6 | 233 | 83.1% | -0.16 | -0.90 | **+0.070** |
| Run6 | **run6-nojudge** | Qwen3-8B | **32B(真实)** | **无** | 1e-6 | 229 | **100%** | -0.43 | -1.08 | **+0.130** |

> 详细分析见各分支 README：[Run4](https://github.com/Ctrl-Alt-Wang/OnPolicy-openclaw/tree/run4/runs/run4) · [Run5](https://github.com/Ctrl-Alt-Wang/OnPolicy-openclaw/tree/run5-opcd/runs/run5) · [Run6](https://github.com/Ctrl-Alt-Wang/OnPolicy-openclaw/tree/run6-nojudge/runs/run6)

---
Run1:
<img width="2445" height="885" alt="image" src="https://github.com/user-attachments/assets/edb07f31-4b11-44f9-8c42-b485ef5b63ba" />
Run2:
<img width="2421" height="900" alt="image" src="https://github.com/user-attachments/assets/0d327d5e-24d7-4c04-996c-1ef04792190c" />
Run3:
<img width="2406" height="926" alt="image" src="https://github.com/user-attachments/assets/02d327e8-b1b6-45e0-b07e-891c8e954e2e" />
Run4:
<img width="2400" height="903" alt="image" src="https://github.com/user-attachments/assets/30e2da9a-3d0b-4fb2-b1b5-d2f19fb70b27" />

## 核心发现：替身问题（Surrogate Teacher Problem）

**这是贯穿 Run1~5 的根本缺陷，在 Run6 中被解决。**

### 什么是替身问题？

在 OPCD/OPSD 框架中，teacher logprobs 不是在原始问题 `x` 上计算的，而是在 hint-augmented 上下文 `x + hint` 上计算的：

```
原始问题（student 推理时见到的）:
  User: "请问糖尿病二型如何治疗？"

hint-augmented（teacher 计算 logprobs 时见到的）:
  User: "请问糖尿病二型如何治疗？"
  Hint: "你的回答遗漏了生活方式干预，应补充饮食控制和运动疗法..."

student 学习目标: max P_teacher(y | x + hint)
student 推理时: 只能用 P_student(y | x)
→ 训练目标和推理场景不对齐！
```

这个 hint-augmented teacher 是真实 teacher 的"替身"——它被 hint 操控，其分布不代表真实大模型在自然问题上的分布。

### 量化证据

| 指标 | Run5（有 judge，替身）| Run6（无 judge，真实） |
|---|---|---|
| 初始 loss | **-0.16**（KL 散度被 hint 压缩）| **-0.43**（真实知识差距） |
| 末步 loss | -0.90 | **-1.08** |
| 接受率 | 83.1% | **100%** |
| 评测 delta | +0.070 | **+0.130（+86%）** |

> Run5 的 -0.16 初始 loss 揭示了问题：hint-augmented teacher 和 student 的分布人为地很接近，真正的知识差距被掩盖了。Run6 的 -0.43 才是 8B vs 32B 的真实距离。

### 各 Run 失败/成功原因链

```
Run1（lr=5e-7, 自蒸馏）→ delta -0.053
  ↓ 问题: 自蒸馏无法引入新知识 + hint 质量受限于模型自身

Run2/3（GPT-5.4 judge, 自蒸馏）→ N/A（步数太少/loss W型）
  ↓ 改进: judge 质量提升
  ↓ 问题: teacher 仍是自身，替身问题依旧

Run4（lr=2e-6，自蒸馏）→ delta -0.090
  ↓ 问题: LR 过大（loss 不收敛）+ 自蒸馏循环游戏

Run5（32B teacher + GPT judge）→ delta +0.070
  ↓ 改进: 真实大模型 teacher 带来真实知识差距
  ↓ 问题: 替身问题（hint-augmented 上下文）+ 17% 样本被丢弃

Run6（32B teacher + 无 judge）→ delta +0.130 ✓
  ✓ 修复: teacher 在原始上下文计算 logprobs，消除替身
  ✓ 修复: 100% 样本接受率，包括正向对齐信号
```

---

## 目录

- [整体架构与原理](#整体架构与原理)
- [训练流程步骤](#训练流程步骤)
- [环境配置](#环境配置)
- [数据集准备](#数据集准备)
- [脚本说明](#脚本说明)
- [Bug 记录与修复](#bug-记录与修复)
- [超参数分析](#超参数分析)
- [训练日志分析](#训练日志分析)
- [评测结果](#评测结果)
- [经验总结与教训](#经验总结与教训)
- [下一步计划](#下一步计划)

---

## 整体架构与原理

### OPSD 是什么？

**OPSD（Online Policy Self-Distillation，在线策略自蒸馏）** 是本项目第一轮训练采用的方法，属于 OPD（Online Policy Distillation）框架的一种变体，对应学术论文中的 OPCD（On-Policy Continual Distillation，arXiv 2602.12275）。核心思想：

```
传统离线蒸馏（SFT）:
  Teacher 生成数据 → 收集完整数据集 → 离线训练 Student

OPCD（在线策略蒸馏）:
  每一轮对话 → Student 当场生成回答
            → Judge 评估 + 生成 Hint
            → Teacher（同模型 + Hint）算 logprobs
            → 立刻梯度更新 Student
            → 更新后的 Student 参与下一轮
```

"在线"的含义：训练信号来自**当前策略自身的输出**，而不是预先收集的静态数据。每条对话都是用-完-即-训。

### 为什么 OPD 的 loss 是负数？

OPD loss 定义为：

```
loss = -(teacher_logprob - student_logprob)
```

- `teacher_logprob`：teacher（同模型 + hint augmentation）对 student 回答 token 序列的对数概率
- `student_logprob`：student 自身对这些 token 的对数概率

当 teacher 比 student 更"认可"这些 token 时（teacher_logprob > student_logprob），loss 为负——**这是正常的、期望的状态**，说明 hint 提供了有效的改进方向，模型正在被往更好的分布拉动。

### Self-OPCD vs OPD with External Teacher

| | OPSD Run 1 | OPSD + 外部 judge（Run 2） | 真正的 OPD（理论，暂不可行）|
|--|--|--|
| **Judge** | 本地 Qwen3.5-9B | **GPT-5.4（外部 API）** | 更强外部模型 |
| **Teacher**（提供 logprobs） | 本地 Qwen3.5-9B | 本地 Qwen3.5-9B | **更强外部模型（需要 logprobs）** |
| **Student** | Qwen3.5-9B | Qwen3.5-9B | 小模型 |
| teacher = student？ | ✅ 是（自蒸馏） | ✅ 是（仍然自蒸馏） | ❌ 否 |
| Hint 质量 | 受限于自身能力 | **更强**，GPT 见过更多知识 | 最强 |
| 闭源模型可行？ | ✅ | ✅ | ❌（需要 logprobs） |
| 成本 | 纯本地 | 每条调用 3 次 GPT API | — |

**关键洞察**：闭源大模型（GPT-4/Claude）没有 logprobs，但可以作为 **judge/hint 生成器**，而 teacher logprobs 仍然由本地模型提供。这是完全合法的架构。

### 框架组件关系图

```
训练循环
  │
  ├── 对话线程（send_training_conversations）
  │     每条 HuatuoGPT 数据 → Turn 1 + Turn 2 → OPD Server
  │
  ├── OPD Server（port 30010，OpenClaw-RL）
  │     接收对话 → 记录 student 回答 → next_state 触发 judge
  │     │
  │     ├── Judge（3 票多数）→ 提取 hint
  │     │     Self-OPCD:  → SGLang:20000 (Qwen3.5-9B)
  │     │     GPT judge:  → judge_proxy:20001 → GPT-5.4 API
  │     │
  │     └── Teacher logprobs → SGLang:20000 (Qwen3.5-9B)
  │           hint-augmented prompt → 重新算 logprobs
  │
  ├── Sample Queue（output_queue）
  │     攒满 batch_size=16 个 Sample → 触发梯度更新
  │
  └── QLoRA 训练模型
        base: Qwen3.5-9B（4-bit NF4 量化）
        adapter: LoRA r=16, alpha=32, target: q/k/v/o_proj
        optimizer: AdamW, lr=5e-7
        每 5 步保存一次 checkpoint
```

---

## 训练流程步骤

### 完整流程（按时序）

```
Step 1: 申请服务器 & 搭建环境
  ├── A800 80GB × 1（117.50.216.160，SSH port 23）
  ├── CUDA 12.8（镜像名 cuda130，实际 nvcc 版本为 12.8）
  ├── Python 3.12（conda env: py312）
  ├── pip install: torch 2.11+cu130, sglang 0.5.12, slime 0.2.2, peft, bitsandbytes
  └── 上传代码：D:\OnPolicy → /workspace/OnPolicy/

Step 2: 启动 SGLang 推理服务
  ├── 模型：Qwen3.5-9B（/workspace/Qwen3.5-9B，从 ModelScope 下载）
  ├── 端口：20000
  ├── 关键参数：--mem-fraction-static 0.3（防 OOM）
  └── 重要：enable_thinking=False（禁用思维链，避免回答被截断）

Step 3: 准备数据集
  ├── 训练集：train_huatuo_2000.jsonl（HuatuoGPT，12科室各166条）
  └── 评测集：eval_huatuo_200.jsonl（同源 hold-out，严格去重，0重叠）

Step 4: 收集 Baseline（训练前快照）
  ├── 脚本：run_collect_baseline.py → SGLang API
  ├── 必须在训练前跑，否则 before/after 对比无效
  └── 输出：/workspace/eval_results/baseline_responses.jsonl

Step 5: Self-OPCD 训练
  ├── 脚本：run_self_opd.py
  ├── OPD Server port: 30010，PRM/judge port: 20000（Self）
  ├── 对话结构：Turn1(question) + Turn2(reference答案作为next_state)
  ├── 110 步，每步 ~3 分钟，约 5.5 小时
  └── WandB 追踪：http://103.139.212.228:3005/johnson/medical-opd

Step 6: 评测 & 对比
  ├── 推理方式：transformers 4-bit（因为合并的LoRA无法被SGLang加载）
  ├── run_eval_base_tf.py → baseline_responses_tf.jsonl
  ├── run_eval_lora.py → trained_responses.jsonl
  ├── run_score.py → GPT-5.4 打分 → score_comparison_tf.jsonl
  └── 结果：Baseline 3.574 → Trained 3.521（-0.053）

Step 7: GPT-5.4 Judge 训练（当前进行中）
  ├── 启动 judge_proxy.py（port 20001）
  │     return_logprob=False → GPT-5.4 API（judge/hint生成）
  │     return_logprob=True  → SGLang:20000（teacher logprobs）
  └── 修改 OPDArgs.prm_router_port = 20001
```

---

## 环境配置

### 服务器信息

| 项目 | 配置 |
|------|------|
| GPU | NVIDIA A800-SXM4-80GB × 1 |
| 显存 | 80 GB |
| CPU | 16 核 |
| 内存 | 240 GB |
| 系统盘 | 178 GB（已用 33 GB）|
| CUDA | 12.8（nvcc，镜像名 cuda130 ≠ 实际版本） |
| Python | 3.12（conda env: py312）|

### 关键依赖版本

```
torch           2.11.0+cu130
sglang          0.5.12.post1
slime           0.2.2
transformers    4.57.6（需 >=4.57 以支持 Qwen3.5）
peft            最新
bitsandbytes    最新
wandb           0.27.0
```

### SGLang 启动命令

```bash
# 训练期间（低显存分配给 KV cache，腾出空间给训练）
python -m sglang.launch_server \
  --model-path /workspace/Qwen3.5-9B \
  --port 20000 \
  --mem-fraction-static 0.3 \
  --served-model-name Qwen3.5-9B
```

**为什么是 0.3**：SGLang 默认 mem-fraction=0.9，会占满 70+ GB，训练的 QLoRA 前向没有空间。设 0.3 后 SGLang 占 ~25 GB，留 ~55 GB 给训练。

---

## 数据集准备

### 训练集：HuatuoGPT-sft-data-v1

- **来源**：[FreedomIntelligence/HuatuoGPT-sft-data-v1](https://huggingface.co/FreedomIntelligence/HuatuoGPT-sft-data-v1)
- **总量**：226k 条真实医患对话
- **采样**：12 科室各 166 条，共 2000 条，`random.seed(42)`
- **字段**：`{instruction, output, dept}`
- **科室**：内分泌代谢、心血管、呼吸、消化、肾脏泌尿、神经、感染免疫、外科骨科、妇产儿科、急诊重症、药理用药、检验影像

### 评测集：HuatuoGPT Hold-out

- **来源**：同一数据集，但**严格排除训练集**（MD5 指纹去重，0 重叠）
- **数量**：200 条（12 科室各 16-17 条）
- **意义**：与训练同域（同格式、同难度），before/after 对比有效

> **为什么不用 CMB**：最初使用 CMB-Exam 作为评测集，但发现其包含考研政治、护理等与华佗训练域不一致的科目（训练-评测域不匹配），改为华佗 hold-out 后对比更公平。

---

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `scripts/sample_datasets_v2.py` | 从 HuatuoGPT 采样训练集，12科室均衡 |
| `scripts/sample_eval_huatuo.py` | 采样评测集，严格去重 |
| `scripts/run_self_opd.py` | **核心**：Self-OPCD 训练主脚本（WandB 集成）|
| `scripts/judge_proxy.py` | **GPT judge 代理**：路由 judge→GPT-5.4，teacher→SGLang |
| `scripts/run_collect_baseline.py` | 训练前通过 SGLang 收集 baseline 回答 |
| `scripts/run_eval_lora.py` | 训练后通过 transformers+LoRA 收集回答 |
| `scripts/run_eval_base_tf.py` | 同等方式收集 baseline（公平对比用）|
| `scripts/run_score.py` | GPT-5.4 对 baseline vs trained 打分对比 |
| `scripts/merge_bf16.py` | 将 LoRA adapter 合并到 bf16 base model |

---

## Bug 记录与修复

### Bug 1：`element 0 of tensors does not require grad`

**现象**：训练第一步后立即崩溃，`avg_loss.backward()` 报错。

**根因**：训练目录里已有旧的 `lora_checkpoints/latest`（上次测试留下的），脚本在加载 checkpoint 时走了 `if os.path.exists(lora_latest):` 分支，但该分支**缺少** `prepare_model_for_kbit_training(base)` 调用。这个函数负责为 4-bit 量化模型启用梯度流，跳过后 LoRA 参数虽然存在，但梯度无法通过冻结的 base 层传播。

**修复**：将 `prepare_model_for_kbit_training` **移到 if/else 之前**，无论是新建还是续训都先调用：

```python
# 修复前（有Bug）
if os.path.exists(lora_latest):
    base = AutoModelForCausalLM.from_pretrained(...)
    model = PeftModel.from_pretrained(base, lora_latest)  # 没有prepare
else:
    base = AutoModelForCausalLM.from_pretrained(...)
    base = prepare_model_for_kbit_training(base)           # 只在新建时调用
    model = get_peft_model(base, lora_cfg)

# 修复后
base = AutoModelForCausalLM.from_pretrained(...)
base = prepare_model_for_kbit_training(base)               # 始终调用
if os.path.exists(lora_latest):
    model = PeftModel.from_pretrained(base, lora_latest, is_trainable=True)  # 加 is_trainable=True
else:
    model = get_peft_model(base, lora_cfg)
```

### Bug 2：Thinking Chain 混入回答

**现象**：收集到的回答都是 "Thinking Process: 1. Analyze the Request..." 英文思维链，实际医学答案被截断。

**根因**：Qwen3.5-9B 默认启用 thinking mode（内置 chain-of-thought），500 token 的 `max_tokens` 远不够容纳完整思维链+答案。

**修复**：在所有 API 调用中加入 `"chat_template_kwargs": {"enable_thinking": False}`，同时 OPD server 的对话调用也要加（因为 OPD server 会透传非标准字段）。

```python
# 修复：所有 SGLang 推理调用均加此参数
json={
    ...,
    "chat_template_kwargs": {"enable_thinking": False},
}
```

### Bug 3：CUDA OOM（多次）

**现象**：训练过程中报 `torch.OutOfMemoryError: CUDA out of memory`。

**根因分析**：

1. **旧 SGLang 进程未释放显存**：`kill` 命令杀死进程后，CUDA context 未被 OS 立刻回收，`nvidia-smi` 显示 `[Not Found]` 进程仍占用 26 GB，导致后续训练可用显存不足。

2. **Qwen3.5-9B 是 Mamba 混合架构**：前向传播中的 `chunk_gated_delta_rule` 操作的激活内存随 `MAX_LEN` 二次增长，远超普通 Transformer。`MAX_LEN=1024` 时训练进程占 ~50 GB。

**修复**：
- `MAX_LEN: 1024 → 256`（医学 QA 典型答案 100-200 tokens，256 足够）
- `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`（防止内存碎片）
- SGLang `--mem-fraction-static: 0.3`（压缩 KV cache，腾出训练空间）
- 操作前彻底清理所有 GPU 进程再重启

### Bug 4：合并后的 LoRA 模型 SGLang 无法加载

**现象**：将 QLoRA 合并后的模型用 SGLang 加载，报错 `Qwen3_5ForCausalLM has no SGlang implementation`。

**根因**：用 `AutoModelForCausalLM.from_pretrained` 加载 Qwen3.5-9B 时，transformers 将其识别为 `Qwen3_5ForCausalLM`，但 SGLang 支持的是原始的 `Qwen3_5ForConditionalGeneration` 架构（两者对应不同的 `config.json` 中 `architectures` 字段）。合并 LoRA 时也保存了新的 architectures 值，导致 SGLang 找不到对应实现。

**解决方案**：评测时改用 transformers 直接推理（不经过 SGLang），确保 baseline 和 trained 使用完全相同的推理路径（都是 transformers 4-bit），消除推理方式不一致带来的误差。

### Bug 5：`max_tokens` vs `max_completion_tokens`

**现象**：调用 GPT-5.4 API 时返回 400 错误：`'max_tokens' is not supported, use 'max_completion_tokens' instead`。

**修复**：将所有对 GPT-5.4 的调用中 `max_tokens` 改为 `max_completion_tokens`。

```python
# GPT-5.4 专用
r = httpx.post(GPT_URL, json={
    "model": "gpt-5.4",
    "messages": [...],
    "max_completion_tokens": 30,  # 不是 max_tokens
    "temperature": 0,
}, ...)
```

---

## 超参数分析

### 训练超参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `lr` | `5e-7` | 极小的学习率。OPD 是在线训练，每步只更新少量 token，过大 lr 会导致 loss 剧烈波动甚至发散 |
| `batch_size` | 16 | 每攒 16 个 OPD Sample 才做一次梯度更新。太小不稳定，太大等待时间长 |
| `MAX_LEN` | 256 | 截断序列长度。主要是为了控制 Mamba 架构的激活内存；医学 QA 一般 100-200 tokens 足够 |
| `save_every` | 5 | 每 5 步保存一次 LoRA checkpoint |
| `max_new_tokens`（Student）| 400-405 | 对话 Turn 1 的生成长度限制 |

### QLoRA 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `load_in_4bit` | True | NF4 量化，节省约 75% 显存 |
| `bnb_4bit_compute_dtype` | bfloat16 | 计算时用 bf16，精度/速度均衡 |
| `bnb_4bit_use_double_quant` | True | 对量化系数再量化，额外节省 ~0.4 bits/weight |
| `lora_r` | 16 | LoRA 秩，影响适配器容量和参数量 |
| `lora_alpha` | 32 | 缩放因子，等效学习率 = lr × alpha/r = lr × 2 |
| `target_modules` | q,k,v,o_proj | 只对 attention 投影层加 LoRA，不包含 FFN（Mamba 层不加）|
| `lora_dropout` | 0.05 | 轻微正则化 |
| `trainable params` | 2,228,224 / 8,956,031,488 | 仅 0.025% 参数可训练 |

### OPD Server 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `prm_m` | 3 | Judge 投票次数（多数票决定接受/拒绝）|
| `prm_temperature` | 0.7 | Judge 的生成温度（适度随机）|
| `prm_max_new_tokens` | 1024 | Judge 输出最大长度 |
| `distill_topk` | 0 | 使用 token-level KL 而非 top-k |

### 训练数据设计

```
Turn 1（驱动 student 生成）：
  messages = [system: "你是专业医学助手", user: <instruction>]
  → Student 生成回答（被 OPD 记录 logprobs）

Turn 2（提供 next_state，触发 judge）：
  messages = [..., assistant: <student_reply>, user: "参考一个更优秀的回答：<ref[:300]>"]
  → 参考答案的前 300 字符作为 next_state
  → Judge 看 student 回答 vs 参考答案，提取改进 hint
```

**设计原理**：OPD 的"信号"来自 next_state——下一条消息。我们把华佗的参考答案作为 next_state，模拟"用户指出更好答案"的场景，judge 可以比较 student 和参考答案的差距，生成有针对性的 hint。

---

## 训练日志分析

### 第一轮：Self-OPCD（Qwen3.5-9B judge）

**运行时间**：约 5.5 小时（2026-06-01 22:53 → 2026-06-02 07:25）

**总体数据**：

| 指标 | 数值 |
|------|------|
| 总步数 | 110 |
| 总样本数 | 1760 |
| 接受率 | 88%（1760/2000）|
| 每步耗时 | ~3 分钟 |
| 最终 avg_loss | -0.8354 |

**Loss 趋势分析**：

```
Step 1:    loss=-0.7829  avg=-0.7829  （起点）
Step ~30:  avg≈-0.8600  （最低点）
Step 110:  loss=-0.7994  avg=-0.8354  （终点）
```

- **Step 1-30 avg_loss 下降**：student 与 teacher（hint augmented）的分布差距在扩大，说明 hint 提供了有效的改进方向，student 还没学到
- **Step 30-110 avg_loss 缓慢回升**：student 开始追上 teacher，gap 逐渐缩小——这是**正常的收敛迹象**
- **每步 loss 波动大（-0.55 到 -1.23）**：因为 12 个科室的医学问题难度差异大，有些 student 本来就答得好（gap 小），有些差（gap 大）

**关键日志片段**：

```
# OPD Pipeline 正常工作的标志
22:54:36 submitted sample index=0 prompt_len=54 response_len=405 hint_len=350
22:58:47 Step 1 | loss=-0.7829 | avg_loss=-0.7829 | tokens=4003 | queue=1

# judge 评分示例（3票多数）
[OpenClaw-OPD] PRM eval session=xxx eval_votes=[-1,-1,-1] eval_score=-1.0
[OpenClaw-OPD] session=xxx accepted hint_len=311 votes=[1,1,1]
# 注：eval_votes 和 judge_votes 是两个独立的评估，前者评估质量，后者决定是否接受

# 训练结束
07:25:48 对话线程结束且队列为空，训练完成
110 步 | Loss 趋势: -0.7829 → -0.7994 ↓ 下降
```

**Tokens per step 分析**：

- 前 105 步稳定在约 4000 tokens/step（16个样本 × 平均 250 tokens）
- 第 108 步：2645 tokens（对话线程开始耗尽，最后几个 batch 不满）
- 第 109-110 步：510, 255 tokens（最后1-2个样本凑的 batch）

### 评测结果详解

**评测方法**：
- Judge：GPT-5.4（外部 API）
- 评分维度：准确性、完整性、简洁性（各 1-5 分，取平均）
- 推理方式：两边均用 transformers 4-bit，确保公平

**结果**：

```
Baseline avg score:  3.574
Trained  avg score:  3.521
Delta:               -0.053
```

| 科室 | Baseline | Trained | Delta |
|------|---------|---------|-------|
| 肾脏泌尿 | 3.44 | 3.69 | +0.25 ✅ |
| 药理用药 | 3.56 | 3.65 | +0.08 ✅ |
| 呼吸 | 3.60 | 3.67 | +0.06 ✅ |
| 急诊重症 | 3.58 | 3.58 | 0.00 |
| 外科骨科 | 3.44 | 3.40 | -0.04 |
| 消化 | 3.56 | 3.50 | -0.06 |
| 神经 | 3.69 | 3.61 | -0.08 |
| 内分泌代谢 | 3.60 | 3.48 | -0.12 |
| 妇产儿科 | 3.50 | 3.37 | -0.13 |
| 检验影像 | 3.64 | 3.49 | -0.15 |
| 心血管 | 3.48 | 3.31 | -0.17 |
| 感染免疫 | 3.75 | 3.52 | -0.23 |

---

## 经验总结与教训

### 1. `prepare_model_for_kbit_training` 必须在加载 adapter 之前调用

这是 QLoRA 训练中最容易忽略的坑。无论是新建 LoRA 还是续训，都要先 prepare base model，否则梯度无法流过冻结层。

### 2. Qwen3.5-9B 是 Mamba 混合架构，激活内存远超普通 Transformer

训练时必须：
- 设置 `MAX_LEN ≤ 256`（256 就够医学 QA 用了）
- 设置 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`
- SGLang `--mem-fraction-static ≤ 0.35`（给训练留足空间）

### 3. 使用 Thinking Model 必须显式关闭 thinking

Qwen3.5-9B 默认开启 thinking mode，收集到的回答全是 chain-of-thought 而非实际答案。所有推理调用都要加：
```python
"chat_template_kwargs": {"enable_thinking": False}
```

### 4. OPD 的 judge 和 teacher 用同一个 `_prm_url`

OpenClaw-OPD 通过 `return_logprob` 字段区分两类调用：
- `False` → judge/eval（只需文本生成）
- `True` → teacher logprobs（需要 SGLang 的 `/generate` 端点）

利用这个特性可以写代理服务器，让外部 LLM 只处理 judge 调用，本地 SGLang 处理 teacher logprobs 调用。

### 5. Self-OPCD 的效果局限

Self-OPCD 的 teacher 是同一个模型加上 hint，理论上限等于"如果这个模型知道 hint 的内容，它能多好"。如果模型本身对某个科室的知识不足，生成的 hint 质量也不高，形成负反馈。这解释了为什么感染免疫、心血管等下降——那些科室对模型来说本来就难，自己评自己效果有限。

### 6. 合并 QLoRA 后无法用 SGLang 加载

`merge_and_unload()` 后保存的模型，`config.json` 中 `architectures` 从 `Qwen3_5ForConditionalGeneration` 变成了 `Qwen3_5ForCausalLM`，后者没有 SGLang 实现。**评测阶段直接用 transformers 推理更简单**，不需要重新走 SGLang。

### 7. 训练和评测推理方式必须一致

首次评测时，baseline 用 SGLang（thinking OFF，greedy），trained 用 transformers 4-bit，两者推理实现细节不同（注意力实现、采样算法），导致结果不可比。改成两边都用 transformers 4-bit 后，结果更可信。

---

## 下一步计划

### 进行中：GPT-5.4 Judge 训练

架构变化：`prm_router_port = 20001`（指向 judge_proxy.py 代理）

- Judge（hint 生成）→ GPT-5.4 API（质量更高）
- Teacher logprobs → 本地 SGLang:20000（不需要外部 logprobs）

预期效果：GPT-5.4 能生成更准确、更有针对性的 hint，特别是对感染免疫、心血管等难度较高的科室。

### 后续可探索

1. **接入线上 nanobot**：目前 nanobot 使用闭源 API（无 logprobs），需要单独部署本地模型实例作为 student，线上流量做 next_state
2. **增加训练步数**：110 步对 9B 模型偏少，建议 500+ 步才能看到稳定趋势
3. **DPO/GRPO**：完全绕开 logprobs 的方式，可以直接用 GPT-4 做偏好打标
4. **更大的参考答案窗口**：当前 next_state 只取参考答案前 300 字，可以尝试全量或摘要化

---

## WandB 追踪

- 项目：http://103.139.212.228:3005/johnson/medical-opd
- Run 1（Self-OPCD）：`qwen3.5-9b-opcd-lr5e-07-bs16`，110 步
- Run 2（GPT judge）：进行中








真正的OPD需要达到的条件
<img width="1401" height="894" alt="image" src="https://github.com/user-attachments/assets/fddfc10d-b44b-427b-941e-49441e90f00e" />
<img width="1541" height="657" alt="image" src="https://github.com/user-attachments/assets/447a49a4-eeb4-471e-9dd3-2e6f5ccc3509" />
<img width="1557" height="906" alt="image" src="https://github.com/user-attachments/assets/e55f741a-1b83-4eeb-a62f-5ac990bb6ed8" />
<img width="1446" height="834" alt="image" src="https://github.com/user-attachments/assets/97d74423-df7a-4315-a98a-288815fa0f97" />
<img width="1158" height="804" alt="image" src="https://github.com/user-attachments/assets/f08b27f5-cd12-4bd9-b7e2-8cb286d97686" />


第一次训练曲线（tokens最后一步暴跌是因为数据收集的不够batch-size了）：
<img width="2436" height="801" alt="image" src="https://github.com/user-attachments/assets/4a437929-ce99-419a-b6c8-8588a5aea1bb" />





