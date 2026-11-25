# experiment-result-anomaly-interpreter

Deterministic, standard-library-only interpreter for one experimental readings table. One
command turns a case into trend, anomalies, supported causes, review steps and follow-up
experiments, with every conclusion traceable to a row, column, threshold or file hash.

## Quick start

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out ./out/result.json --work ./work
python bench/run_bench.py          # optional: skill vs naive baseline, writes bench_report.md
```

Exit code is 0 on success, on partial data and on malformed input; a structured
`result.json` is always written.

## Input

`case.json` is required. Recognised keys (any nesting depth):

| key group | keys | meaning |
|---|---|---|
| identity | `case_id` | echoed unchanged into `result.json` |
| contract | `output_contract` | fields the caller requires at the top level of `result.json` |
| readings | `readings`, `measurements`, `data`, `observations`, `rows`, `table`, `values`, `points`, `records` | list of row objects, list of row arrays with a header, or a dict of equal-length columns |
| thresholds | `outlier_z`, `z_threshold`, `anomaly_z`; `saturation_max`, `range_max`, `detector_max`, `upper_limit`; `saturation_min`, `range_min`, `detector_min`, `lower_limit` | override the defaults (robust z 3.5) |
| context | `metadata`, `instrument`, `controls`, `groups`, `unit_note` | copied into data-quality notes where relevant |

If the case has no inline rows, the skill reads the first usable sibling table in the case
directory (`.csv`, `.tsv`, `.txt`) or any path named by a `*_file` / `*_path` key. A delimited
table needs at least two data rows and one numeric column; the first non-numeric row is taken
as the header. Column names do not need to be English: time-like and value-like columns are
matched by name first, then by monotonicity and numeric density.

## Output

`result.json` always contains `case_id`, `status` and every `output_contract` key, plus:

| field | content |
|---|---|
| `trend` | overall direction; per-series blocks live in `result.series_trends` |
| `anomalies` | row number, x, value, robust z, direction, series and raw row |
| `causes` | candidates ranked by evidence, each with `supported` and evidence text |
| `review_steps` | actions a second person can execute, bound to row numbers and fields |
| `next_experiments` | added controls, replicates, denser sampling or narrowed ranges |
| `data_quality` | rows, column mapping, missing values, duplicates, saturations, unit notes |
| `claims` | five segments (trend / anomaly / cause / review / next) each with an evidence pointer |
| `unexplained` | candidates that the table cannot support, undeclared units, series without replicates |
| `confirmations` | items that need a human confirmation (threshold choice, batch/channel attribution) |
| `evidence` | case file name and SHA-256, column map, thresholds, row-numbering rule |
| `stats` | row, series, anomaly, level-shift and saturation counts |

One run also writes `report.md` (human-readable), `validation.json` (eight self-checks with
`all_passed`) and `provenance.json` (input names, sizes and SHA-256 hashes; no absolute paths).

## Decision rules

1. Series = distinct combination of the detected group columns (batch / channel / well / sample).
2. Anomaly = per-series robust z `|z| >= 3.5` on median and MAD; MAD zero falls back to IQR/1.349;
   zero robust scale means only saturation is checked.
3. Plateau = spread of the last three points within 2% of the last value.
4. Level shift = within-series step or between-series offset, reported with rows and a score.
5. Saturation = reading at or beyond the declared detector range; reported separately from anomalies.
6. Causes are ranked by evidence strength (batch, channel, time drift, saturation, sample/handling);
   without group columns they stay "to be checked" rather than being assigned.

## Status semantics

| status | condition |
|---|---|
| `success` | numeric response found, every series has at least two points, no saturation, groups present |
| `partial` | single-point series, no group column, saturation, or unit mismatch |
| `insufficient_input` | no readings, or no numeric response column |
| `failed` | case file missing or not valid JSON (empty skeleton still written) |

## Dependencies and limits

- Python 3.8+, standard library only; no network access.
- No multiple-testing correction, kinetic model fitting or causal inference.
- Never invents replicates, controls or causes; unsupported items go to `unexplained`.
- Does not modify the input data; only row numbers are referenced.

## Layout

```
SKILL.md                 agent-facing contract
README.md                this document
scripts/run_skill.py     single entry point
scripts/publish_artifacts.py  report / validation / provenance writer
examples/demo-case/      synthetic demo case
bench/cases|gold|run_bench.py   fair-comparison harness and gold labels
templates/               reusable threshold config and review checklist
```
