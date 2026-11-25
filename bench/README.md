# Bench — result interpretation

This folder holds the fair-comparison harness behind the "使用增益 / 创新增益" claims for
`challenge-8354c69a`. It does not assert gains in prose: every number in
`bench_report.md` / `bench_metrics.json` is produced by running the shipped skill and a
documented baseline over the same case files.

## Protocol

| item | value |
|---|---|
| inputs | `bench/cases/*.json` (plain case files, same schema as `examples/demo-case/case.json`) |
| gold labels | `bench/gold/*.json`, written before running either side |
| skill side | one command per case: `python scripts/run_skill.py --case <case> --out <tmp>/result.json --work <tmp>/work` |
| baseline side | the rule a generic agent applies to one flat table: single global mean/SD filter with `\|z\| >= 3`, no per-series grouping, no level-shift test, no instrument-range check |
| scoring | identical gold labels and identical metric code for both sides |

## Cases and what each one isolates

| case | planted truth | why the naive baseline misses it |
|---|---|---|
| `c1_batch_offset_spike` | a +180 spike inside batch A (row 4) while batch B sits ~295 units higher | between-batch offsets inflate the global SD, so the spike stays under 3 global sigma |
| `c2_three_batch_spike` | a +280 spike confined to batch C (row 16) across three batches | same global-variance inflation, three batches instead of two |
| `c3_level_shift` | batch A steps from ~104 to ~144 between rows 5 and 6, no single point is extreme | a global point filter has no notion of a step; nothing exceeds 3 sigma |
| `c4_saturation` | batch B hits the declared ceiling of 1000 on rows 11-12 | the baseline never reads the declared range, so saturation is invisible |

## Metrics

- anomaly TP / FP / FN, precision, recall, F1 (row-level, 1-based row numbers).
- shift cases matched: the predicted level-shift kind and series must match the gold entry
  (for `series_level_shift` the first row after the step is also checked).
- saturation cases matched: the reported saturated-row count equals the gold count.
- unresolved gold targets: missed anomaly rows + missed shifts + missed saturation cases.
  This is the manual rework a reviewer would have to do by hand.
- claims with evidence pointer: claims whose `evidence` field is non-empty, i.e. traceable
  back to a column, threshold or row range.

## Reproduce

```bash
python bench/run_bench.py
```

Writes `bench_metrics.json` and `bench_report.md`. The run is deterministic: no timestamps,
no absolute paths, sorted keys, identical bytes on a second run.

## Known boundaries

- The cases are synthetic and deliberately small; they isolate grouping, step detection and
  range handling, not every failure mode of real instruments.
- The baseline is intentionally simple. It represents a competent generic agent, not the
  weakest possible straw man.
- Gold labels encode only what the case itself makes unambiguous; no hidden threshold tuning.
