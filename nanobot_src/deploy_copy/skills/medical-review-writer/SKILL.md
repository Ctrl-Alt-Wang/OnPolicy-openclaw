---
name: medical-review-writer
description: 医学综述撰写技能。适用于医学叙述性综述、临床综述、研究进展综述、专题综述、证据综述初稿撰写。遇到“写综述”“生成综述大纲”“按大纲检索文献并撰写医学综述”“先搜文献再写综述”“根据 InfoX-Med 文献写 review”时必须触发。该技能遵循 AgenticWriter 的核心流程：先界定主题与大纲，再按章节检索 InfoX-Med 文献，必要时读取全文，最后分节撰写并统一整合。
---

# Medical Review Writer

## 概述

这个技能用于把一个医学综述任务拆成固定的四段流水线：

1. 主题约束与综述边界澄清
2. 大纲生成与章节检索计划
3. 基于 InfoX-Med 的分层检索与全文抽取
4. 按章节写作、统一引用、整合终稿

它不是泛泛“写一篇文章”。它的核心要求是：

- 先有大纲，再写正文
- 每一章写之前都先检索
- 具体数据、结论、年份、样本量只来自已检索文献
- 优先使用指南、系统评价/Meta 分析、RCT 和高质量综述

## 依赖技能

本技能默认联动以下同仓库技能：

- `medical-keyword-search`
- `full-paper-api`

其中：

- `medical-keyword-search` 负责关键词检索、布尔表达式检索、时间和类型筛选
- `full-paper-api` 负责按 `doc_id` 读取 InfoX-Med 全文

如果需要把检索结果整理成综述证据包，使用本技能自带脚本：

- `scripts/build_review_packet.py`
- `scripts/fetch_full_papers.py`

## 适用场景

- 写“某疾病/某机制/某疗法”的医学综述
- 先生成综述大纲，再按章节补全文献并成稿
- 把 InfoX-Med 数据库作为主要证据源来撰写综述
- 需要综述初稿、章节草稿、提纲扩展稿、证据包

不适用：

- 单个临床问题的简短循证回答
- 已有全文成稿，仅需语言润色
- 严格系统评价/Meta 分析中的统计合并

## 默认输入

开始执行时，先从用户请求中明确以下最小信息：

- 综述主题
- 综述类型：叙述性综述 / 临床综述 / 研究进展综述 / 专题综述
- 输出语言：中文或英文
- 时间范围：默认近 5 年优先，必要时补充里程碑研究
- 重点维度：机制 / 流行病学 / 诊疗 / 方法学 / 转化 / 安全性 / 争议点

如果用户没有给全，优先做合理假设；只有在主题边界明显过宽时，才补问 1 个澄清问题。

## 核心流程

### 第 1 步：锁定综述范围

先把用户主题转换成可检索的问题框架。输出内部工作草稿时，至少包含：

- `topic`
- `population_or_disease`
- `intervention_or_focus`
- `review_goal`
- `language`
- `time_window`
- `key_dimensions`

若主题过大，先主动收窄。例如：

- “肺癌免疫治疗综述”收窄为“晚期 NSCLC 中 PD-1/PD-L1 免疫治疗疗效与耐药机制综述”
- “肠道菌群综述”收窄为“肠道菌群与免疫检查点抑制剂疗效相关性的临床与机制综述”

### 第 2 步：先生成大纲，再检索正文证据

大纲必须由文献检索意图驱动，而不是空模板。执行规则：

1. 先提出 8-15 个一级/二级章节
2. 每个章节都要绑定一个检索意图
3. 每个章节预设 2-5 个英文关键词
4. 标出哪些章节优先依赖指南/Meta/RCT，哪些章节需要机理研究或全文补读

建议的大纲骨架：

- 标题
- 摘要
- 引言
- 疾病或研究背景
- 核心机制 / 关键路径
- 临床证据 / 诊疗证据
- 特殊人群 / 亚组 / 场景差异
- 安全性 / 局限性 / 争议点
- 新兴方向与转化挑战
- 结论与展望

注意：章节标题必须贴合主题，不要机械套模板。

### 第 3 步：用 `medical-keyword-search` 做章节化检索

每个大章节写作前，都要先检索，不允许先写后补证据。

#### 推荐检索顺序

1. 全局检索：理解主题全貌
2. 章节检索：补齐当前章节证据
3. 定向检索：处理争议点、特殊人群、机制细节

#### 全局检索命令

```bash
python <skill_directory>/../medical-keyword-search/scripts/medical_search.py all \
  "keyword 1" "keyword 2" "keyword 3" \
  --output /tmp/review_global_search.json
```

#### 指定类别检索命令

```bash
python <skill_directory>/../medical-keyword-search/scripts/medical_search.py systematic-meta \
  "keyword 1" "keyword 2" "keyword 3" \
  --output /tmp/review_meta_search.json
```

```bash
python <skill_directory>/../medical-keyword-search/scripts/medical_search.py rct \
  "keyword 1" "keyword 2" "keyword 3" \
  --output /tmp/review_rct_search.json
```

#### 自由布尔检索命令

```bash
python <skill_directory>/../medical-keyword-search/scripts/medical_search.py free \
  --query '(NSCLC[Title]) AND (PD-1[Title/Abstract]) AND (resistance[Title/Abstract])' \
  --filter '$$doc_publish_time$$2020-01-01$$2026-12-31' \
  --sort docPublishTime \
  --output /tmp/review_free_search.json
```

#### 检索规则

- 关键词优先用英文
- 不把年份直接写进检索式，年份通过 `--filter` 控制
- 优先取近 5 年，必要时追溯经典文献
- 当前章节若涉及疗效结论，优先找指南、Meta、RCT
- 当前章节若涉及机制、分型、转化障碍，补充基础和转化研究
- 同一章节至少保留 5-10 篇可用文献线索

### 第 4 步：把检索结果整理成综述证据包

建议在大纲完成后，先把全局检索结果整理成一个 Markdown 证据包，便于筛文献。

```bash
python <skill_directory>/scripts/build_review_packet.py \
  --input /tmp/review_global_search.json \
  --output /tmp/review_packet.md \
  --top 40
```

这个证据包会输出：

- 去重后的候选文献表
- 分类来源
- `doc_id`
- 标题、期刊、年份、影响因子
- InfoX-Med 链接

使用它来挑选：

- 全局综述核心文献
- 每章必读文献
- 需要补全文的高价值文献

### 第 5 步：用 `full-paper-api` 或本技能脚本拉全文

当出现以下情况时，必须读全文，不要只看摘要：

- 需要具体效应量、样本量、95%CI、亚组结果
- 需要准确描述研究设计、纳排标准、终点定义
- 需要判断争议点到底来自研究对象、方法还是结局差异
- 需要提炼图表或全文讨论中的局限性

可直接调用全文接口：

```bash
curl -s -H "X-Token: e3f62087e126439aa12ad4637cf4f12b|1106970" \
  "http://60.205.166.229:9306/api/v1/paper/doc-id/116"
```

或使用本技能脚本批量拉取：

```bash
python <skill_directory>/scripts/fetch_full_papers.py \
  --doc-id 116 220 335 \
  --output /tmp/review_full_papers.json
```

全文阅读时，优先提取：

- 研究问题
- 研究设计
- 样本与人群
- 干预或暴露
- 主要终点
- 核心结果
- 局限性
- 能否支持当前章节论点

### 第 6 步：按章节写作

正文采用“先检索、后撰写、逐节整合”的方式。

每写一个章节前，都执行以下检查：

1. 当前章节是否已有足够证据
2. 是否包含高等级证据
3. 是否需要全文核验关键数字
4. 是否存在相反结论或争议点

写作要求：

- 先给该章节的核心判断，再展开证据
- 不编造数据、文献、结论
- 区分“已有共识”“证据倾向”“存在争议”“证据不足”
- 把异质性的来源写清楚：人群、方案、终点、随访、研究设计
- 不把摘要里没有的数据写成确定事实

### 第 7 步：整合终稿

完成所有章节后，再统一处理：

- 术语一致性
- 缩写首次全称
- 章节间重复内容去重
- 引用编号统一
- 结论强度与证据等级匹配

如果用户没有明确要求参考文献清单，默认输出：

- Markdown 综述正文
- 关键证据摘要
- 待补全文或待核验点

如果用户要求完整综述稿，则可额外输出：

- 参考文献线索表

## 输出优先级

根据用户请求选择以下一种或多种结果：

### A. 仅大纲

适用于用户说“先给我一个综述大纲”。

输出：

- 标题
- 章节结构
- 每章检索意图

### B. 大纲 + 检索证据包

适用于用户说“先搜文献再定大纲/看有哪些文献可写”。

输出：

- 大纲
- 关键文献表
- 每章建议文献
- 需要读全文的文献列表

### C. 完整综述初稿

适用于用户要求直接写初稿。

输出：

- 标题
- 摘要
- 正文分节
- 结论与展望
- 可选的参考线索表

## 质量红线

- 不允许跳过大纲直接长篇成稿
- 不允许在没有检索支持时生成具体事实
- 不允许把推测写成共识
- 不允许忽略相反证据
- 不允许把检索结果原样堆给用户而不综合
- 不允许把“摘要级证据”伪装成“全文核验结论”

## 推荐执行模板

用户给出主题后，默认按下面顺序执行：

1. 归一化主题并收窄范围
2. 生成综述大纲
3. 做一次全局检索
4. 生成综述证据包
5. 针对章节补检索
6. 对关键文献拉全文
7. 分章节写作
8. 汇总终稿

## 示例

### 示例 1：生成肺癌免疫治疗综述

```bash
python <skill_directory>/../medical-keyword-search/scripts/medical_search.py all \
  "non-small cell lung cancer" "PD-1" "immunotherapy resistance" \
  --output /tmp/nsclc_global.json

python <skill_directory>/scripts/build_review_packet.py \
  --input /tmp/nsclc_global.json \
  --output /tmp/nsclc_packet.md \
  --top 40
```

### 示例 2：补拉关键全文

```bash
python <skill_directory>/scripts/fetch_full_papers.py \
  --doc-id 116 220 335 \
  --output /tmp/nsclc_fulltext.json
```

## 一句执行摘要

写医学综述时，先定边界和大纲，再按章节调用 `medical-keyword-search` 检索，用 `full-paper-api` 读取关键全文，最后基于已核验证据生成综述初稿。
