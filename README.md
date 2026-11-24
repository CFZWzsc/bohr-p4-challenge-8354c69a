# Runtime contract

Bohrium Playground Period 4 submission — challenge `challenge-8354c69a` (track: `experimental-design`).

This repository holds the complete skill package for the challenge: the skill
definition, its executable pipeline and all supporting documents. No precomputed
answers, private data or credentials are included.

## Skill

- Name: `experiment-result-anomaly-interpreter`
- Summary: Use when an experimental-design case supplies measured readings, curves or instrument logs and asks for the trend, which points are anomalous, probable causes, and what to re-check or run next; run scripts/run_skill.py for a deterministic, row-traceable interpretation with explicit thresholds.

## Contents

| File |
|------|
| `SKILL.md` |
| `examples/demo-case/case.json` |
| `scripts/run_skill.py` |
| `README.md` |

## How to run

```bash
python scripts/sk_entry.py --input /input --work /app/work --out /app/output
```

A single deterministic pass reads `/input`, computes the deliverable and writes a
contract-complete `/app/output/result.json` plus the human-readable review files
described in `SKILL.md`. The same input always produces byte-identical output; no
network access is used, and fields the materials cannot support are reported
explicitly instead of being left empty.

## Notes

- Pure Python standard library; no network access required.
- Every claim is anchored to paragraph-level evidence; unknown items are reported
  in `uncertainty` instead of being fabricated.
