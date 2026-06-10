# Run7：Seq-KD 序列级知识蒸馏（Qwen3.5-397B-A17B API teacher → Qwen3-8B student，lr=2e-5）

> **结论：Delta=-0.134，Seq-KD 反而劣于 baseline。** 使用 397B API teacher 生成训练数据，8B student 在 teacher 文本上 SFT，但模仿大模型的输出风格导致了分布偏移，损害了 student 自身的医学回答能力。关键发现：SiliconFlow API 不支持 logprobs，API-teacher 真正的 OPD 不可行，Seq-KD 是唯一路线但也存在根本局限。

---

## 1. 实验目的

Run6 使用本地 Qwen3-32B teacher 做 OPD 取得了 delta=+0.130 的效果。本实验探索：**能否用更强的 API teacher（397B 参数）通过 Seq-KD 方式进一步提升？**

### 为什么是 Seq-KD 而非 OPD

OPD（On-Policy Distillation）需要 teacher 在 **student 生成的 response** 上计算 token 级 log probability，要求 teacher 和 student 共享相同的 tokenizer，且 API 需支持 echo/logprobs。

本实验验证了 SiliconFlow API 的能力边界：

| 测试项 | 结果 |
|---|---|
| `/v1/chat/completions` 正常生成 | ✅ 正常 |
| `/v1/completions` + `echo=True` + `logprobs`（Qwen3.5-397B） | ❌ 500 Unknown error |
| `/v1/completions` + `echo=True` + `logprobs`（Qwen2.5-7B） | ❌ 400 "logprobs is not allowed" |
| `extra_body: {prompt_logprobs: 1}` | ❌ 500 Unknown error |

**结论：SiliconFlow 平台层面不支持 logprobs，API-based 真 OPD 对任何模型均不可行。** Seq-KD（让 teacher 生成高质量文本 → student SFT 模仿）是使用 API teacher 的唯一可行路线。

### 额外的 tokenizer 不兼容问题

- Qwen3 系列（8B/32B/72B）：vocab_size = 151,643
- Qwen3.5 系列（9B/397B）：vocab_size = 248,044

即使 API 支持 logprobs，两个系列也无法混用做 OPD（token id 不对应）。Seq-KD 绕过了这个限制，因为只需要 teacher 生成文本，不需要 token 对齐。

---

## 2. 实验配置

### 2.1 整体流程

```
阶段1（数据生成）：
  train_huatuo_2000.jsonl → SiliconFlow API (Qwen3.5-397B-A17B) → seqkd_run7_teacher.jsonl

阶段2（SFT训练）：
  seqkd_run7_teacher.jsonl → Qwen3-8B QLoRA SFT → lora_ckpt_qwen3_8b_seqkd_run7_lr2e5/final
```

### 2.2 配置表

| 参数 | 值 |
|---|---|
| Student 模型 | Qwen3-8B（QLoRA, NF4 量化, r=32, alpha=64） |
| Teacher 模型 | Qwen/Qwen3.5-397B-A17B（API，无 thinking 模式）|
| 训练方法 | Seq-KD（Sequence-level Knowledge Distillation）|
| API 提供商 | SiliconFlow（主）+ Dashscope（补充，余额不足时切换）|
| 学习率 | 2e-5（第一次 1e-6 失败后修正）|
| Epochs | 3 |
| Batch size | 16（per_device=2, grad_accum=8）|
| Max length | 1024 tokens |
| 训练数据 | HuaTuo 2000条（teacher生成，实际有效 1998条）|
| 评测数据 | HuaTuo eval 200条 |
| GPU | 1× NVIDIA A800-SXM4-80GB（GPU0，GPU1 有 zombie memory leak）|
| Wandb run | `a1txhsp9`（`qwen35-397b-teacher-8b-student-seqkd-run7-lr2e5`）|
| Checkpoint | `/workspace/lora_ckpt_qwen3_8b_seqkd_run7_lr2e5/final` |

---

## 3. 数据生成过程

### 3.1 生成脚本

`generate_seqkd_data_run7.py` — 支持断点续传，已完成条目自动跳过。

- System prompt：`"你是一名专业的医学助手，请准确地回答医学问题。"`
- Temperature：0.7，max_tokens：600
- 每次调用间隔 0.3s 限速

### 3.2 执行过程（双 API 接力）

| 阶段 | API | 生成条数 | 结果 |
|---|---|---|---|
| 第一轮 | SiliconFlow | 1076/2000 | ❌ 余额不足，中途中断 |
| 第二轮（续传） | Dashscope | 922/924 剩余 | ✅ 0 错误 |
| **合计** | | **1998/2000** | 2条在第一轮已失败且无法补救 |

生成耗时：约 11 小时（SiliconFlow 8-9s/条；Dashscope ~3.3s/条）。

### 3.3 数据样例

Teacher（397B）的回答风格为结构化的 Markdown 格式，包含 `###` 标题、`**加粗**` 和 `*bullet list*`，比 baseline（Qwen3-8B 原始输出）更长更结构化。这一点后来被认为是影响评测结果的关键因素。

---

## 4. 训练过程

### 4.1 第一次尝试（失败）：lr=1e-6，2 epochs

从 OPD 训练脚本（Run6）复制超参数，lr=1e-6。

| 指标 | 值 |
|---|---|
| 步数 | 238 |
| 训练时长 | 13 分钟 |
| train loss | 1.72 → 1.646（仅降 4.6%）|
| eval loss | 1.644（≈ train loss，明显欠拟合）|

**根因**：SFT 是普通交叉熵，lr=1e-6 比标准 SFT lr（2e-5）小 20 倍，模型几乎没有更新。

### 4.2 第二次训练（正式）：lr=2e-5，3 epochs

| 指标 | 值 |
|---|---|
| 步数 | 357 |
| 训练时长 | 约 21 分钟 |
| train loss | 1.70 → 1.20（下降 30%）|
| eval loss（epoch1）| 1.265 |
| eval loss（epoch2）| 1.215 |
| eval loss（epoch3）| **1.21** |

Loss 曲线表现健康：
- 前 100 步快速下降（1.70 → 1.30）
- 100 步后趋于平稳（1.30 → 1.20）
- train loss ≈ eval loss，无过拟合
- grad_norm 从 0.65 快速降至 0.2 后稳定，训练正常收敛

**技术问题记录**：
- `Trainer.__init__() unexpected keyword argument 'tokenizer'`：transformers 5.9 将该参数改名为 `processing_class`，已修复
- GPU1 zombie memory leak（72GB 残留，进程已不存在）：切换至 GPU0（80GB 全空闲）解决

---

## 5. 评测结果

### 5.1 总体得分

| 指标 | 值 |
|---|---|
| Baseline avg score（Qwen3-8B 未训练） | **3.212** |
| Run7 Seq-KD avg score | **3.078** |
| **Delta** | **-0.134** |
| 评测对数 | 200 |
| 评测模型 | GPT-5.4（准确性/完整性/清晰度，各1-5分，取均值）|

### 5.2 Per-department 详细结果

| 科室 | Baseline | Run7 | Delta | 趋势 |
|---|---|---|---|---|
| 妇产儿科 | 3.04 | 3.08 | **+0.04** | ↑ |
| 感染免疫 | 3.19 | 2.92 | **-0.27** | ↓ 明显退化 |
| 呼吸 | 3.31 | 3.33 | **+0.02** | → 持平 |
| 急诊重症 | 3.54 | 3.31 | **-0.23** | ↓ 退化 |
| 检验影像 | 3.33 | 3.11 | **-0.22** | ↓ 退化 |
| 内分泌代谢 | 3.27 | 3.12 | **-0.15** | ↓ 退化 |
| 神经 | 3.19 | 3.08 | **-0.11** | ↓ 小幅退化 |
| 肾脏泌尿 | 3.21 | 3.02 | **-0.19** | ↓ 退化 |
| 外科骨科 | 3.21 | 2.92 | **-0.29** | ↓ 最大退化 |
| 消化 | 3.36 | 3.10 | **-0.25** | ↓ 退化 |
| 心血管 | 3.00 | 2.98 | **-0.02** | → 持平 |
| 药理用药 | 2.83 | 2.94 | **+0.11** | ↑ 唯一明显提升 |

**3/12 科室提升，9/12 科室退化。** 退化最大：外科骨科（-0.29）、感染免疫（-0.27）。

---

## 6. 为什么 Seq-KD 表现更差：机制分析

### 6.1 分布偏移（核心原因）

397B teacher 的回答风格与 Qwen3-8B 自身的输出分布有显著差异：

| 特征 | Qwen3-8B（baseline）| 397B teacher |
|---|---|---|
| 回答长度 | 相对简洁 | 较长，含 markdown 结构 |
| 格式 | 流畅段落 | `###` 标题 + `**加粗**` + bullet list |
| 语气 | 直接回答 | 更学术、分层展开 |

SFT 强制 8B 模仿 397B 的输出风格，导致：
- 模型语言模式被改变（学会了 markdown 结构）
- 但医学知识并未从 teacher 真正传递到 student（Seq-KD 是文本级模仿，非分布级对齐）
- GPT-5.4 评测关注医学**内容质量**，而非格式，因此格式变了但分数反而下降

### 6.2 Off-policy 的根本局限

OPD 和 Seq-KD 的本质区别：

```
OPD（Run6）：
  student 生成回答 → teacher 在 student 回答上打分 → 优化 student 向 teacher 分布靠近
  → On-policy：teacher 在 student 当前的输出上给信号，梯度方向精准

Seq-KD（Run7）：
  teacher 生成回答 → student 模仿 teacher 的文本 → cross-entropy loss
  → Off-policy：teacher 的输出是 teacher 自己的分布，student 被迫离开自身分布
```

当 teacher 比 student 强很多（397B vs 8B），teacher 的输出分布与 student 相差极大，强行模仿导致 student 能力退化，类似于让小学生强背博士论文——背下来了格式，但理解力反而下降。

### 6.3 Run6 OPD 不存在这个问题

Run6 的 teacher（32B）在 student（8B）**自己生成的回答**上打分，信号方向是"如何让你现有的回答更接近 32B 的分布"，而非"丢掉你的回答，模仿我的"。这是 OPD 在理论上优于 Seq-KD 的核心原因。

### 6.4 药理用药是正向异常

药理用药（+0.11）是唯一明显提升的科室，可能原因：
- 该科室本身格式化信息多（药品名、剂量、禁忌），teacher 的结构化格式恰好匹配评测期望
- 该科室 baseline 分数最低（2.83），存在较大提升空间

---

## 7. 与其他 Run 完整对比

| 维度 | Run4 | Run5 | Run6 | **Run7** |
|---|---|---|---|---|
| Student | 9B | 8B | 8B | **8B** |
| Teacher | 9B(self) | 32B(local) | 32B(local) | **397B(API)** |
| 方法 | OPD+judge | OPD+judge | OPD | **Seq-KD** |
| On/Off policy | On | On | On | **Off** |
| Teacher 上下文 | hint+原始 | hint+原始 | 原始 | **N/A（teacher生成文本）** |
| 接受率 | ~83% | 83.1% | 100% | **N/A** |
| 数据量 | 2000 | 2000 | 2000 | **1998（teacher生成）** |
| 最终 train loss | — | -0.90 | -1.08 | **1.20（CE loss，不可比）** |
| eval loss | — | — | — | **1.21** |
| Delta | -0.090 | +0.070 | +0.130 | **-0.134** |
| 结论 | 退化 | 初步有效 | 最佳 | **退化** |

---

## 8. 局限性与后续改进方向

### 8.1 Seq-KD 的固有问题

- **无法做 on-policy**：teacher 的文本是固定的，student 训练中生成分布变化后无法重新获取 teacher 信号
- **分布差距越大效果越差**：teacher 越强，输出风格与 student 差异越大，SFT 模仿难度越高
- **格式污染**：397B 的结构化输出可能影响 student 的自然语言能力

### 8.2 可能的改进

1. **过滤 teacher 数据**：只保留 teacher 回答中与 baseline 风格相近（长度、格式接近）的样本
2. **DPO/ORPO**：用 teacher 回答作为 chosen，student baseline 回答作为 rejected，做偏好对齐而非直接 SFT
3. **本地大模型 OPD（Run8 计划）**：使用 Qwen3-235B-A22B-FP8（ModelScope 可下载，~235GB FP8，4×A800 可运行），恢复 on-policy 优势

### 8.3 API OPD 的彻底不可行

本实验同时验证了 API-based 真 OPD 的不可行性：
- SiliconFlow：不支持任何形式的 logprobs（平台级限制）
- Dashscope：支持 chat completions 生成，但 logprobs 未经测试（预期同样不支持）
- 即使 API 支持 logprobs，Qwen3（151k vocab）和 Qwen3.5（248k vocab）tokenizer 不兼容，也无法混用

---

## 9. 文件索引

| 文件 | 路径 |
|---|---|
| 数据生成脚本 | `/workspace/generate_seqkd_data_run7.py` |
| SFT 训练脚本 | `/workspace/run_seqkd_run7.py` |
| Teacher 生成数据 | `/workspace/data/seqkd_run7_teacher.jsonl`（1998条）|
| 训练日志（lr=1e-6） | `/workspace/logs/sft_run7.log` |
| 训练日志（lr=2e-5） | `/workspace/logs/sft_run7_lr2e5.log` |
| Wandb run | `http://103.139.212.228:3005/johnson/medical-opd/runs/a1txhsp9` |
| Checkpoint | `/workspace/lora_ckpt_qwen3_8b_seqkd_run7_lr2e5/final/` |
| 评测生成脚本 | `/workspace/run_eval_qwen3_8b_seqkd_run7.py` |
| 打分脚本 | `/workspace/run_score_seqkd_run7.py` |
| 评测输出 | `/workspace/eval_results/trained_qwen3_8b_seqkd_run7.jsonl` |
| 评测得分 | `/workspace/eval_results/score_comparison_seqkd_run7.jsonl` |
| API logprobs 测试 | `/workspace/test_echo_logprobs.py`、`test_echo_logprobs2.py`、`test_echo_logprobs3.py` |
| .env（API 密钥） | `/workspace/opd_project/.env`（gitignored）|
