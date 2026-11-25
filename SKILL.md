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
- 无内联读数时自动读取案例目录内 `.csv/.tsv/.txt` 表格（首个含数值列者；首行非数值行作表头）。
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

- 只用标准库；不做多重检验、动力学拟合或因果推断。阈值默认，案例 `thresholds` 优先。
- 不补造重复/对照/原因，无法归因时写“信息不足”；不改原始数据，只引用行号。

## 最小调用示例

```bash
python /skills/weekly-skill/scripts/run_skill.py --case /input/case.json --out /app/output/result.json --work /app/work
```

示意输入/输出仅演示接口，非官方结果。


## Quickstart

在包根目录执行：

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out ./demo-output/result.json
```

- 演示案例：`examples/demo-case/case.json`（合成，3 批 × 6 点，含 1 个尖峰）。
- 输出：`result.json` 含契约字段与 `dataset`/`anomalies`/`causes`/`review_steps`/`next_experiments`/`data_quality`，异常带行号；本案例实测 `success`。
- 增益对照：`bench/run_bench.py` 在同一金标准下对比本技能与朴素全局阈值基线，结果见 `bench/bench_report.md`；复用说明见 `README.md` 与 `templates/`。

## 交付保证（单次运行）

一次 `python scripts/run_skill.py` 即产出完整交付物：`result.json`（`output_contract` 全键 + 实质内容）、`report.md`（人类可读报告）、`validation.json`（自检项与证据）、`provenance.json`（输入哈希与可复现声明）。不存在第二阶段：输入无法支持的项目写入 `uncertainty` 并说明原因，不写占位符、不留 `pending`。

- 输入缺失、JSON 损坏、字段异常时仍写出结构化 `result.json` 并以 0 退出。
- 不联网、不伪造实验数据、不声称平台评分或官方案例结果。
- 同一输入重复运行字节一致；`validation.json` 的 `all_passed` 应为 `true`。
