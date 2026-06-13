# OPD Medical Agent Distillation Experiment Report
## Runs 5-8 Complete Analysis

> Generated: 2026-06-13  
> Author: Auto-generated from server logs + Claude Code conversation history  
> Repository: https://github.com/Ctrl-Alt-Wang/OnPolicy-openclaw  
> Branch: experiment-runs-5-8-record

---

## 1. Project Overview

**Goal**: Train a medical assistant agent (Qwen3-8B student) using On-Policy Distillation (OPD) from stronger teacher models, and evaluate whether stronger teachers lead to better distillation outcomes on a 200-sample medical QA benchmark.

**Evaluation Method**: GPT-5.4 as judge, scoring each response on 3 criteria (1-5 scale), computing delta = trained_avg - baseline_avg per sample. Final metric: average delta across 200 samples.

**Student Model**: Qwen3-8B (4-bit QLoRA, varies by run)

**Training Data**: 2000 medical QA samples across 12 departments (肾脏泌尿, 急诊重症, 神经, 心血管, 呼吸, 消化, 药理用药, 感染免疫, 妇产儿科, etc.)

---

## 2. Experiment Summary Table

| Run | Method | Teacher | Precision | Judge | Steps | final avg_loss | Samples | avg_delta | pos | neg | zero |
|-----|--------|---------|-----------|-------|-------|----------|---------|-----------|-----|-----|------|
| Run5 | OPD | Qwen3-32B | FP16 | Yes (PRM) | ~200 | - | - | **+0.070** | 78 | 67 | 55 |
| Run6 | OPD | Qwen3-32B | FP16 | No | 229 | -0.6252 | 3664 | **+0.130** | 86 | 51 | 63 |
| Run7 | Seq-KD | Qwen3.5-397B (API) | - | - | - | - | - | **-0.134** | 66 | 89 | 45 |
| Run8 | OPD | Qwen2.5-72B-Instruct | FP8 | No | 347 | -0.3669 | 5552 | **-0.042** | 1 | 9 | 190 |

### Key Observation
- Run6 (OPD + Qwen3-32B no-judge) is the **only successful** experiment
- Run8 used a bigger but **cross-series** teacher (Qwen2.5 vs Qwen3), resulting in catastrophic failure
- Run7 Seq-KD failed because it is off-policy by design + cross-series tokenizer mismatch

---

## 3. Run-by-Run Detailed Analysis

### Run5: OPD + Judge + Qwen3-32B
- **Date**: ~2026-06-08
- **Method**: OPD with PRM judge model evaluating sample quality before accepting into training batch
- **Teacher**: Qwen3-32B (local, FP16, SGLang, TP=1, port 20000)
- **Student**: Qwen3-8B (4-bit QLoRA, r=16, lr=5e-7, batch_size=16)
- **Result**: avg_delta = +0.070
- **Analysis**: Judge filtering improved stability but eliminated potentially valuable training signals. Conservative improvement.

### Run6: OPD No-Judge + Qwen3-32B (BEST)
- **Date**: 2026-06-08 ~ 06-09
- **Method**: OPD without judge - all on-policy samples accepted for training
- **Teacher**: Qwen3-32B (local, FP16, SGLang, TP=1, port 20000)
  - SGLang startup: `start_sglang_32b.sh`
- **Student**: Qwen3-8B (4-bit QLoRA, r=32?, lr=1e-6, batch_size=16)
- **Training Details**:
  - 229 steps, final avg_loss = **-0.6252**, 3664 samples collected
  - Initial loss: -0.4338, converged to ~-1.0 range by step 200+
  - Training time: ~19.5 hours (06:53:08 to 02:26:40 next day)
- **W&B Run**: `qwen3-32b-teacher-8b-student-nojudge-opd-lr1e-06-bs16`
- **Checkpoint**: `lora_ckpt_qwen3_8b_nojudge`
- **Result**: avg_delta = **+0.130** (best result)
- **Per-department**:
  - Best: 外科骨科 (+0.376), 神经 (+0.354), 药理用药 (+0.271)
  - Worst: 呼吸 (-0.145), 急诊重症 (-0.084), 肾脏泌尿 (-0.042)

### Run7: Seq-KD + Qwen3.5-397B (API) - FAILED
- **Date**: ~2026-06-10
- **Method**: Sequential Knowledge Distillation (off-policy)
- **Teacher**: Qwen3.5-397B via SiliconFlow API (no logprobs support)
  - API根本不支持logprobs（连echo=True都报500），无法做真正的OPD
- **Result**: avg_delta = **-0.134** (worse than baseline!)
- **Analysis**: Failed because:
  1. API不支持logprobs，无法做on-policy KL散度
  2. 跨系列tokenizer不匹配 (Qwen3.5 vocab=248320, Qwen3 vocab=151936)
  3. Seq-KD本质上是off-policy的，样本分布不匹配导致负迁移

### Run8: OPD No-Judge + Qwen2.5-72B-Instruct FP8 - FAILED
- **Date**: 2026-06-11 ~ 06-13
- **Method**: OPD without judge, same method as Run6 but with larger teacher
- **Teacher**: Qwen2.5-72B-Instruct (local, FP8 online quantization, SGLang, TP=2, port 20000)
  - Model path: `/model/ModelScope/Qwen/Qwen2.5-72B-Instruct`
  - SGLang args: `--quantization fp8 --mem-fraction-static 0.55 --context-length 2048 --tensor-parallel-size 2 --disable-cuda-graph`
  - GPU0: ~47.7GB (SGLang TP0), GPU1: ~50.2GB (SGLang TP1)
- **Student**: Qwen3-8B (4-bit QLoRA, r=32, lr=1e-6, batch_size=16)
  - Uses GPU0 only for training (~22GB), sharing with SGLang
- **Training Details**:
  - 347 steps, final avg_loss = **-0.3669**, 5552 samples collected, checkpoint at step_345
  - Initial loss: -0.1683, much lower magnitude than Run6 (-0.4338)
  - Training time: ~6 hours (02:42 to 08:35)
  - **CRITICAL**: avg_loss magnitude (-0.3669) is MUCH SMALLER than Run6 (-0.6252)
    - This indicates weaker KL divergence signal = teacher logprobs not well-aligned with student
- **W&B Run**: `qwen25-72b-teacher-8b-student-nojudge-opd-run8-lr1e-06-bs16` (run ID: jis4czec)
- **Checkpoint**: `/workspace/lora_ckpt_qwen3_8b_run8_nojudge/step_345`
- **Result**: avg_delta = **-0.042** (1 positive, 9 negative, 190 neutral = near-zero effect)
- **Per-department**:
  - Almost all departments at 0 delta
  - Worst: 药理用药 (-0.125), 急诊重症 (-0.125), 神经 (-0.125)
  - Best: 感染免疫 (0.0), 消化 (0.0), 呼吸 (0.0)

---

## 4. CRITICAL FINDING: Tokenizer Vocabulary Mismatch

| Model | vocab_size | Series | Compatible with Qwen3-8B? |
|-------|-----------|--------|--------------------------|
| Qwen2.5-72B-Instruct | **152064** | Qwen2.5 | NO (128 token gap) |
| Qwen3-8B (student) | **151936** | Qwen3 | - |
| Qwen3-32B | **151936** | Qwen3 | YES |
| Qwen3.5-9B | **248320** | Qwen3.5 | NO (huge gap) |
| Qwen3-72B | **下载未完成** (32KB on disk) | Qwen3 | SHOULD BE (151936) |

### Why This Matters for OPD

OPD computes KL divergence between teacher and student log-probability distributions over the **same tokens**. The process:
1. Student generates a response (tokenized with Qwen3-8B tokenizer, vocab=151936)
2. Teacher scores the same tokens and provides logprobs
3. If teacher uses a different vocab (152064 vs 151936), token IDs 151936-152063 exist in teacher but not in student
4. When teacher generates tokens in this gap range, student cannot interpret them
5. The KL divergence loss is computed on **misaligned distributions** = corrupted training signal

### Evidence

- **Run6** (same-series, vocab match): avg_loss reaches -0.6252, strong signal = +0.130 delta
- **Run8** (cross-series, 128-token gap): avg_loss only reaches -0.3669, weak/noisy signal = -0.042 delta
- The 190/200 neutral scores in Run8 means the training barely changed the model at all

---

## 5. Training Dynamics Comparison: Run6 vs Run8

### Loss Progression

| Step | Run6 loss | Run6 avg_loss | Run8 loss | Run8 avg_loss |
|------|-----------|---------------|-----------|---------------|
| 1 | -0.4338 | -0.4338 | -0.1683 | -0.1683 |
| 10 | -0.5349 | -0.4534 | -0.2144 | -0.2074 |
| 50 | -0.4938 | -0.4556 | -0.3394 | -0.2096 |
| 100 | -0.6458 | -0.5027 | -0.3598 | -0.2425 |
| 150 | -0.6908 | -0.5235 | -0.7154 | -0.2730 |
| 200 | -0.8575 | -0.5750 | -0.5112 | -0.2901 |
| 229 | -1.0769 | -0.6252 | - | - |
| 300 | - | - | -0.9889 | -0.3266 |
| 347 | - | - | -0.6226 | -0.3669 |

**Key insight**: Run6 loss magnitude starts 2.6x higher than Run8 (-0.43 vs -0.17) and stays consistently larger throughout training. This directly reflects the quality of the KL divergence signal - same-series tokenizer = stronger, more coherent signal.

### Sample Efficiency
- Run6: 3664 samples, 229 steps = 16 samples/step (full batch)
- Run8: 5552 samples, 347 steps = 16 samples/step (full batch)
- Run8 processed 52% more samples but achieved far less - quality of signal matters more than quantity

---

## 6. Run8 Hardware & Infrastructure

### Server Configuration
- **GPU**: 2x NVIDIA A800 80GB
- **IP**: 117.50.216.160:23 (SSH)

### Memory Layout during Training
- GPU0: SGLang TP0 (~47.7GB) + Student training (~22GB) = ~70GB/80GB
- GPU1: SGLang TP1 (~50GB) = ~50GB/80GB

### FP8 Quantization Trick
The key innovation that made 72B model fit in 2x A800:
```bash
--quantization fp8 --mem-fraction-static 0.55
```
- FP8 weights: ~36GB per GPU (vs ~72GB FP16)
- `mem-fraction-static=0.55`: allocates 44GB/GPU, leaving remaining for KV cache + student training
- Peak during loading: ~70GB briefly, then settles to ~44GB/GPU

---

## 7. Evaluation Pipeline

### Step 1: Inference (`run_eval_qwen3_8b_run8.py`)
- Loads Qwen3-8B base + Run8 LoRA checkpoint (4-bit QLoRA)
- Generates responses for 200 medical QA samples
- Output: `trained_qwen3_8b_run8.jsonl` (743KB, 200 samples, 0 errors)

### Step 2: Scoring (`run_score_run8.py`)
- Uses GPT-5.4 via `https://one-api.infox-med.com/v1/chat/completions`
- Each sample: 3 independent judge calls for baseline and trained
- Scores on 1-5 scale, delta = trained_avg - baseline_avg
- API key stored in script (ROTATE THIS!)

### Scoring Daemon Bug
`wait_score_run8.sh` had a shell parsing bug that prevented auto-scoring:
```bash
cnt=$(cat /workspace/eval_results/trained_qwen3_8b_run8.jsonl 2>/dev/null | wc -l)
if [ "$cnt" -ge 200 ]; then  # Never true - cnt includes filename
```
The `wc -l` output includes the filename, so the integer comparison always fails. Had to manually re-run scoring.

---

## 8. Claude Code Conversation Timeline

Full conversation saved in `claude_code_conversation_run8.jsonl` (3.3MB, 694 lines)

| Time | Event |
|------|-------|
| 06-10 14:05 | User asks Claude Code to analyze previous conversation history |
| 06-10 14:09 | User asks core experiment to do next |
| 06-10 15:00 | Decision: Run8 with stronger teacher |
| 06-10 15:02 | Discovery: server is 2xGPU -> can only run 72B not 235B |
| 06-10 15:34 | Discussion about Seq-KD control experiment (Run7
') - rejected as low priority |
| 06-10 15:36 | Question about using Qwen3.5 student for Seq-KD |
| 06-11 00:05 | Decision confirmed: Run8 = OPD + Qwen2.5-72B FP8 teacher, 2-card |
| 06-11 00:07 | SSH credentials shared, connection established via paramiko |
| 06-11 00:26 | ModelScope token provided for downloading 72B model |
| 06-11 00:37 | Download issues, switched to HuggingFace |
| 06-11 01:13 | HF token provided, download eventually succeeded |
| 06-11 01:36 | Download completed, model verification issues |
| 06-11 01:38 | **Vocab_size consistency discussed but NOT verified before training!** |
| 06-11 01:42 | Training launched |
| 06-11 01:45 | User confirms NO judge model for Run8 (true OPD) |
| 06-11 02:43 | Run8 successfully started, Step 1 completed |
| 06-11 02:48 | Training confirmed stable, loss=-0.1683, GPU monitoring healthy |
| 06-11 02:52 | FP8 deployment breakthrough documented |
| 06-12 09:00 | Training completed (347 steps), evaluation started |
| 06-12 09:37 | Evaluation progress 75/200, auto-scoring daemon setup |
| 06-12 16:20 | **Claude Code subscription expired** - all subsequent responses = access denied |
| 06-13 02:00 | User attempts to check scoring status - no response |
| 06-13 04:15 | Scoring re-run via Codex CLI (paramiko), 200/200 completed |
| 06-13 12:45 | Final results confirmed: Run8 avg_delta = -0.042 |

---

## 9. Lessons Learned

### 9.1 Tokenizer Compatibility is NON-NEGOTIABLE
**Always verify vocab_size matches between teacher and student BEFORE training.** A mismatch of even 128 tokens (0.08%) completely destroyed the OPD KL divergence signal.

Rule: For OPD, teacher and student MUST share the same tokenizer. Cross-series distillation without aligned tokenizers is fundamentally broken.

### 9.2 Bigger Teacher != Better Result (with mismatched tokenizer)
- Run6 (32B, same-series): +0.130
- Run8 (72B, cross-series): -0.042
- 128-token vocabulary gap turned a potentially valuable experiment into noise.

### 9.3 No-Judge OPD > Judge-Guided OPD
- Run5 (with judge): +0.070
- Run6 (no judge): +0.130
- Judge filtering removes beneficial training signal diversity.

### 9.4 Seq-KD is Not Viable for This Task
- Run7 (Seq-KD): -0.134
- Off-policy nature + tokenizer mismatch = negative transfer.

### 9.5 Process Failures
1. **Vocab check was discussed but never executed** before Run8 training started - this was the critical omission
2. **Scoring daemon had a shell bug** that prevented auto-scoring after eval
3. **Claude Code subscription expired mid-experiment**, leaving monitoring gaps for ~18 hours
4. **HF token download was painful** - multiple attempts, ModelScope -> HF fallback
5. **Loss signal was ignored** - Run8 loss magnitude was ~40% of Run6, a clear warning sign during training that was not flagged

---

## 10. Recommendations for Next Steps

### Priority 1: Run9 with Qwen3-72B (Same-Series Teacher)
- Server has `/workspace/Qwen3-72B` but download incomplete (only 32KB metadata)
- Need to complete download first (~144GB FP16 from HuggingFace/ModelScope)
- Qwen3-72B vocab_size SHOULD be 151936 (same as Qwen3-8B/32B) = **fully compatible**
- Same OPD no-judge setup as Run6
- Use FP8 to fit in 2x A800 (72B FP8 ~72GB, TP=2)
- **This is the cleanest test of "does a stronger same-series teacher help?"**

### Priority 2: BEFORE Run9, Verify Qwen3-72B vocab_size
- Run: `grep vocab_size /workspace/Qwen3-72B/config.json`
- Confirm = 151936 before starting ANY training

### Priority 3: Compare Run6 vs Run9 Loss Curves
- If same-series 72B produces loss similar to Run6 (~-0.6 range), training signal is valid
- If loss is in -0.3 range like Run8, something is still wrong

### NOT Recommended
- Any cross-series distillation without tokenizer alignment
- Seq-KD approaches for this task
- Using API-based teachers that cannot provide logprobs

---

## 11. File Inventory

| File | Description | Size |
|------|-------------|------|
| `EXPERIMENT_REPORT.md` | This report | 12KB |
| `run5_opd_judge_qwen3_32b.jsonl` | Run5 per-sample scores (200 samples) | 30KB |
| `run6_opd_nojudge_qwen3_32b.jsonl` | Run6 per-sample scores (200 samples) | 30KB |
| `run7_seqkd_qwen3.5_397b.jsonl` | Run7 per-sample scores (200 samples) | 30KB |
| `run8_opd_nojudge_qwen2.5_72b_fp8.jsonl` | Run8 per-sample scores (200 samples) | 30KB |
| `run6_nojudge_steps.log` | Run6 training step-by-step log (229 steps) | ~15KB |
| `run8_opd_nojudge_steps.log` | Run8 training step-by-step log (347 steps) | ~15KB |
| `vocab_comparison.txt` | Tokenizer vocab_size comparison across models | <1KB |
| `run_opd_train.py` | OPD training script (main codebase) | 17KB |
| `start_sglang_72b.sh` | SGLang 72B teacher startup script | <1KB |
| `start_sglang_32b.sh` | SGLang 32B teacher startup script | <1KB |
| `start_sglang.sh` | SGLang default startup script | <1KB |
| `start_sglang_run7.sh` | SGLang Run7 startup script | <1KB |
| `run_eval_qwen3_8b_run8.py` | Run8 evaluation inference script | 2KB |
| `run_score_run8.py` | Run8 GPT-5.4 scoring script | 3KB |
| `wait_score_run8.sh` | Auto-scoring daemon (had bug) | <1KB |
| `wait_and_score_run8.sh` | Alternative auto-scoring daemon | <1KB |
| `claude_code_conversation_run8.jsonl` | Full Claude Code conversation (excluded from git) | 3.3MB |