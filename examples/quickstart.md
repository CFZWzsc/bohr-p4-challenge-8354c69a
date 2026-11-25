# Quickstart — experiment reading analysis package

Minimal end-to-end run. Python 3.10+ standard library only, no network access.

## 1. Run the bundled demo case

```bash
python scripts/run_skill.py --case examples/demo-case/case.json --out result.json
```

Expected, on this demo case (byte-identical across runs):

- `status` = `success`
- `anomalies` = 1 entry at row 16 (batch C, time 90, robust z = 6.36)
- `level_shifts` = `[]` (the remaining rows follow a smooth trend)
- `causes` = 2 ranked candidates, `review_steps` = 5, `next_experiments` = 2
- `result` carries every key declared in `output_contract`

Read the numbers back:

```bash
python -c "import json; d=json.load(open('result.json')); print(d['status'], d['stats'])"
```

## 2. Point it at your own table

Write `my-case.json` with a row list and an output contract:

```json
{
  "case_id": "my-run",
  "readings": [
    {"batch": "A", "channel": 1, "time_min": 0, "absorbance": 0.11},
    {"batch": "A", "channel": 1, "time_min": 30, "absorbance": 0.24}
  ],
  "threshold": 3.5,
  "output_contract": {"trend": "object", "anomalies": "array", "causes": "array"}
}
```

```bash
python scripts/run_skill.py --case my-case.json --out result.json
```

Column roles are inferred (`time`, `value`, `group`) but can be pinned:

```json
{"columns": {"time": "time_min", "value": "absorbance", "group": ["batch", "channel"]}}
```

## 3. What the thresholds mean

- `threshold` (default 3.5): robust z cut-off for a single-point anomaly.
- Level-shift tests report only steps that clear four times the within-segment
  scatter, so a steady ramp is reported as a trend, not as a step.
- Rows already reported as anomalies are removed before the level-shift tests,
  so one spike cannot manufacture a step.

If a case has no reading table, the script writes a `status="missing_input"`
result with the missing keys and still exits 0.
