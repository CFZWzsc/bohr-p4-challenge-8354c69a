# Bench — skill vs naive global threshold

Protocol: identical case files and gold labels for both sides; the baseline is one global
mean/SD filter (|z| >= 3) with no per-series grouping, no level-shift test and no range check.
Gold labels: `bench/gold/*.json`; cases: `bench/cases/*.json`. Reproduce: `python bench/run_bench.py`.

| metric | skill | baseline |
|---|---|---|
| anomaly TP / FP / FN | 2 / 0 / 0 | 0 / 0 / 2 |
| anomaly precision | 1.0 | 0.0 |
| anomaly recall | 1.0 | 0.0 |
| anomaly F1 | 1.0 | 0.0 |
| shift cases matched | 3/3 | 0/3 |
| saturation cases matched | 1/1 | 0/1 |
| unresolved gold targets | 0 | 6 |
| claims with evidence pointer | 33 / 33 | 0 / 0 |
| artifacts written per run | 4 | 0 |

## Per case

| case | anomaly TP/FP/FN | shift ok | saturation ok |
|---|---|---|---|
| bench-01-batch-offset-spike | 1/0/0 | True | n/a |
| bench-02-three-batch-spike | 1/0/0 | True | n/a |
| bench-03-level-shift | 0/0/0 | True | n/a |
| bench-04-saturation | 0/0/0 | n/a | True |

## Baseline per case

| case | anomaly TP/FP/FN | shift ok | saturation ok |
|---|---|---|---|
| bench-01-batch-offset-spike | 0/0/1 | False | n/a |
| bench-02-three-batch-spike | 0/0/1 | False | n/a |
| bench-03-level-shift | 0/0/0 | False | n/a |
| bench-04-saturation | 0/0/0 | n/a | False |

Interpretation: the gap comes from per-series robust statistics (median/MAD), the
level-shift test and the declared-range check. The baseline misses the planted spike
whenever between-batch offsets inflate the global variance, and it never reports a step
or a saturation row. All numbers above are produced by this run, not asserted by hand.
