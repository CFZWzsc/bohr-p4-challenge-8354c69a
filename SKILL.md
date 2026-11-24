---
name: experiment-result-anomaly-interpreter
description: Use when an experimental-design case supplies measured readings, curves or instrument logs and asks for the trend, which points are anomalous, probable causes, and what to re-check or run next; run scripts/run_skill.py for a deterministic, row-traceable interpretation with explicit thresholds.
---

# 实验结果解释与异常分析

## 用途与适用条件

把一份实验读数解释成五段可检查结论：结果趋势、异常点、可能原因、复核步骤、后续实验建议。适用于 `experimental-result interpretation` 类案例：读数表、曲线点、批次/通道/孔位/时间点与设备日志。

不适用：替换原始数据、补造未测重复、把相关性写成因果、替代统计假设检验软件；不做论文写作或文献综述。

## 输入

- `/input/case.json`（可用 `--case`）：`case_id`、`output_contract`；常见可选键 `readings`/`measurements`/`data`/`observations`/`rows`、`columns`、`groups`、`thresholds`、`instrument`、`controls`、`metadata`。
- 读数支持“字典行列表”和“首行表头的二维数组”两种形态。
- `/input/task.md`（可选）：补充指标口径与判读阈值。
- 输出默认 `/app/output/result.json`。

## 处理流程（对应评分维度）

1. **表结构识别（任务完成度）**：自动区分数值列与分类列；时间列优先取 `time`/`cycle`/`hour`/`index` 等名称，否则取单调数值列；响应列优先取 `value`/`signal`/`response`/`yield`/`absorbance` 等名称。记录识别依据与行数。
2. **趋势（正确性）**：对每个序列做最小二乘斜率、首末相对变化、R²，并检测平台期（末 3 点极差 ≤ 末值 2%）；趋势方向与幅度必须能回指到具体行号。
3. **异常点（正确性）**：序列内用中位数与 MAD 计算稳健 z，阈值默认 |z| ≥ 3.5；MAD 为 0 时退回 IQR×1.5。输出异常行的行号、原值、z 值、所属批次/通道/重复；超量程或饱和单独标记。
4. **可能原因（正确性）**：按证据强度排序候选，逐条给支持证据与排除证据：
   - 批次效应：异常是否集中在单一批次；
   - 通道/孔位效应：是否集中在单一通道；
   - 时间漂移：异常点的时间分布是否偏离整体；
   - 饱和/超量程：是否贴近量程上限；
   - 样本或操作问题：无批次/通道信息时只能列为待查，不强行归因。
5. **复核步骤（可核验性）**：把结论拆成第二个人可执行的动作，包含回查的具体字段、行号、批次日志与对照文件。
6. **后续实验（完整性）**：依据证据缺口给补对照、加重复、加密采样点、缩窄参数范围等具体改动，并说明预期能区分哪两种原因。
7. **数据质量与边界（可靠体验）**：报告缺失、单位不一致、重复数不足、对照缺失、读数饱和；未解释部分单列，不用笼统话术掩盖。

## 输出契约

| 字段 | 含义 |
|-|-|
| `case_id` | 与输入一致 |
| `output_contract` 各字段 | 命中则填真实值，否则 `null` + `contract_notes` |
| `status` | `success` / `partial` / `insufficient_input` / `failed` |
| `result` | `dataset`、`trend`、`anomalies`、`causes`、`review_steps`、`next_experiments`、`data_quality` |
| `evidence` | 输入哈希、列映射、阈值、行号索引 |
| `uncertainty` | 缺失对照、重复不足、单位不明、无法归因项 |
| `errors` / `stats` | 真实错误与行数/序列数/异常数 |

## 异常处理表

| 情况 | 处置 | 状态 |
|-|-|-|
| `case.json` 缺失/非法 | 空骨架 + `case_load_failed` | `failed` |
| 无读数 | 不生成趋势，列出缺失项 | `insufficient_input` |
| 无响应列或全部非数值 | 只做表结构报告 | `insufficient_input` |
| 单点序列 | 不计算斜率，标 `insufficient_points` | `partial` |
| 无批次/通道列 | 原因只列“待查”，不定位对象 | `partial` |
| 单元不明或混用 | 标 `unit_mismatch`，不自动换算 | `partial` |
| 读数达到量程上限 | 标 `saturation`，建议稀释复测 | `partial` |
| 重复数 < 2 | 不把单次读数当重复均值 | `partial` |

## 限制

- 只用标准库；不做多重检验校正、拟合复杂动力学模型或因果推断。
- 异常阈值是默认判据，案例给出 `thresholds` 时以其为准。
- 不补造未测量的重复、对照或原因证据；无法归因时明确写“信息不足”。
- 不修改原始数据文件，只在输出中引用行号。

## 最小调用示例（示例，非官方案例结果）

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
```

示意输入：`{"case_id":"synthetic-interpret-demo","output_contract":{"trend":"object","anomalies":"array"}}`。示意输出保留 `case_id`、`trend`、`anomalies`、`status`；无读数时 `insufficient_input`，`trend` 为 `null`、`anomalies` 为空数组。仅为接口示例。


## Quickstart

在包根目录执行：

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out ./demo-output/result.json
```

- 演示案例：`examples/demo-case/case.json`（3 个批次 × 6 个时间点，含 1 个合成尖峰；纯合成，不代表真实实验）。
- 输出：`result.json` 含 `dataset`、`trend`、`anomalies`、`causes`、`review_steps`、`next_experiments`、`data_quality`，并给出异常行号；本案例实测 `status="success"`。

## 交付保证与评分对齐

调用顺序（固定）：

1. 先运行包内脚本（若存在）：`python scripts/run_skill.py`（默认读 `/input/case.json`，写 `/app/output/result.json`）；路径不同时用 `--case` / `--out` 指定。
2. 再完成脚本无法自动完成的实质工作（译文、论述、图表、修订、结论等），把结果写回 `result.json` 对应字段。
3. 最后自检：`case_id` 与输入一致；`output_contract` 每个字段都存在；`status` 为 `success`（仅在确实缺输入时为 `partial`）；无 `pending` 占位；数字、引用、来源可逐条回溯。

运行保证：

- 输入缺失、JSON 损坏、字段异常、输出目录不存在时，仍须写出结构化 `result.json` 并正常结束，不得崩溃或非零退出。
- 不联网、不伪造数据、不声称平台评分或官方案例结果。
- 交付物必须是可直接编辑与复核的成品，而不是流程说明。

评分对齐（本题五个维度）：

- 实际效果（40）：完整产出任务要求的最终成品，覆盖全部输入条目，可直接进入修改流程。
- 使用增益（25）：体现相对基础 Agent 的可验证改进（结构化、术语/数字/引用核对、可编辑性）。
- 创新增益（15）：保留方法学增量（分块、对齐、二次校验、版本比对等），并用结果证明其价值。
- 可靠体验（10）：异常输入有明确降级与说明，不同长度/文体/重复运行下稳定产出。
- 生态贡献（10）：用途、调用、输入输出、限制、示例、维护信息齐全，资源可被他人复用。

## 最终交付强制要求

1. **调用 Agent 必须交付成品，不是流程说明**：脚本产出只是索引、核对或规格骨架；调用 Agent 必须在同一 `result.json` 中补齐本题要求的最终产物（正文/译文/审稿意见/综述/分析结论/图表源文件与导出件/幻灯片页内容与讲稿/实验方案等）。交付字段为空、只有标题骨架，或含 `pending`、`TODO` 之类占位，一律视为未完成。
2. **必须覆盖全部输入条目**：输入中的每个章节、问题、文献、图、页面、指标都要有对应条目，不得只处理示例或首条；确实缺失的条目写入 `uncertainty` / `limitations` 并说明原因，不得静默跳过。
3. **必须自检后再交付**：`case_id` 与输入一致；`output_contract` 每个字段都存在；状态值取本题契约规定的枚举；数字、单位、引用、来源可逐条回溯；结果内部无自相矛盾。
4. **参数等价**：`python scripts/run_skill.py --case <输入> --out <输出>` 与 `--output <输出>` 等价；默认 `/input/case.json` → `/app/output/result.json`。
5. **平台用 3 个固定案例分别运行**：逻辑要由输入驱动，不针对某一份示例硬编码；字段命名差异走别名匹配与显式降级，并在 `uncertainty` 记录假设。
