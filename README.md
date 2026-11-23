# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-8354c69a` (track: `experimental-design`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable entry point and all supporting scripts. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `experiment-result-anomaly-interpreter`
- Summary: Use when an experimental-design case supplies measured readings, curves or instrument logs and asks for the trend, which points are anomalous, probable causes, and what to re-check or run next; run scripts/run_skill.py for a deterministic, row-traceable interpretation with explicit thresholds.

## Contents

| File |
|------|
| `SKILL.md` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/run_skill.py --case /input/case.json --output /app/output/result.json
```

The entry point is `SKILL.md`; input/output contracts, error handling and a minimal
usage example are documented there.

## Notes

- Pure Python standard library; no network access required.
- The result JSON keeps the input case id, the main results, per-item evidence,
  a run status and an uncertainty section.
