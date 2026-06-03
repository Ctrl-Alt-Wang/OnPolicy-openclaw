# Issues CSV 契约指南

借鉴成熟 skill 的「issues CSV 作为契约」设计：把整份基金申请书拆成若干条带状态、
依赖和验收标准的任务行。撰写过程围绕这张表推进，**表是唯一事实来源**。

这套机制天然对应产品里的「分模块 + 总进度条」交互：每条 issue 的状态推进，就是
进度的推进。

## 何时使用

- **写整份申请书** → 从 `assets/issues-template.csv` 复制一份，按用户课题填好，
  然后逐行推进。
- **只写某一两个模块** → 可不建全表，但仍按对应行的规格与验收标准执行。
- **修改优化** → 在表里把对应模块状态从 DONE 退回 DOING，改完再标 DONE。

## 列定义

| 列 | 含义 | 取值 |
| --- | --- | --- |
| `ID` | 任务编号，带阶段前缀 | P1.. / L1.. / C1.. / S1.. / F1.. / V1.. / R1.. |
| `Phase` | 所属阶段 | 准备 / 立项依据 / 内容目标问题 / 方案可行性 / 特色创新 / 计划结果 / 收尾 / 优化 |
| `Module` | 对应 module-specs.md 的模块 | 如「模块8」「选题分析」 |
| `Title` | 该任务产出物 | 简短描述 |
| `Word_Spec` | 字数规格 | 如「2500-3000字」「<400字」「n/a」 |
| `Citation_Need` | 是否需要文献检索 | yes / no；yes 时注明最少条数（如「≥20」） |
| `Citation_Status` | 文献三态 | 见下方「文献三态」 |
| `Depends_On` | 前置依赖任务（分号隔开） | 如「L1;L2;L3」表示需先完成 |
| `Acceptance` | 验收标准 | 标 DONE 的条件 |
| `Status` | 任务状态 | TODO / DOING / DONE / SKIP |
| `Notes` | 备注 | 自由填写 |

## 阶段前缀

- `P` 准备过程（Preparation）
- `L` 立项依据（Lixiang / rationale）
- `C` 研究内容、目标、关键科学问题（Content）
- `S` 研究方案及可行性（Scheme）
- `F` 特色与创新（Feature）
- `Y` 年度计划及预期结果（Yearly）
- `Z` 收尾（参考文献、研究基础汇置）
- `R` 修改优化（Revision）

## 文献三态（Citation_Status）

借鉴成熟 skill 的「结果三态」并改造为文献场景。**绝不编造文献**，每条引用必须如实标注：

- `pending`（待检索）：尚未调用文献检索工具，引用位点为空。
- `placeholder`（占位）：已布设引用位点 `[n]`，但文献条目待检索工具返回后填充。
- `verified`（已核实）：引用来自 InfoX-Med 内部文献检索工具的真实返回，已核对。

铁律：
- 不得把 `placeholder` 谎标为 `verified`。
- 任何需要文献的模块，`Citation_Status` 未达 `verified` 前不得标 `Status=DONE`。
- 检索工具不可用时，如实保留 `placeholder` 并在 Notes 注明，交付时明确告知用户。

## 依赖门控（Depends_On）

标 DONE 前，必须确认 `Depends_On` 列出的所有任务都已 DONE 或 SKIP。
若任一依赖仍是 TODO/DOING，当前任务**不得**标 DONE。此规则不可协商。

典型依赖链（来自思维导图的天然顺序）：
- 研究假设（L3）依赖 研究意义（L1）+ 研究现状（L2）。
- 生成立项依据（L4）依赖 L1;L2;L3。
- 正文各模块（C/S/F/Y）依赖立项依据 L4。
- 收尾参考文献（Z1）依赖所有需要文献的任务都 verified。

## 推进流程

1. 复制模板，按课题填好各行的 Title/Word_Spec/Notes。
2. 选一条 `Depends_On` 已满足的 TODO，置为 DOING。
3. 需要文献则先调用检索工具，更新 `Citation_Status`。
4. 按 `module-specs.md` 规格撰写，达到 `Acceptance` 后置 DONE。
5. 全部 DONE/SKIP 即完成；总进度 = DONE 行数 / 总行数。
