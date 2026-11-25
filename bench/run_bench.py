#!/usr/bin/env python3
"""Fair comparison bench: this skill vs a naive global-threshold baseline.

Both sides read the same case files and are scored against the same gold
labels in bench/gold/. The baseline is the rule a generic agent applies when
it is handed one flat table: a single global mean/SD filter with |z| >= 3,
no per-series grouping, no level-shift test and no instrument-range check.

Run from the package root:  python bench/run_bench.py
Outputs (deterministic): bench/bench_metrics.json and bench/bench_report.md
"""

import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CASES = os.path.join(HERE, "cases")
GOLD = os.path.join(HERE, "gold")
SKILL = os.path.join(ROOT, "scripts", "run_skill.py")
TIME_LIKE = {"time", "t", "index", "x", "cycle", "hour", "minute", "second", "row"}


def load(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def run_skill(case_path, out_dir):
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, SKILL, "--case", case_path,
                           "--out", os.path.join(out_dir, "result.json"),
                           "--work", os.path.join(out_dir, "work")],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=300)
    result_path = os.path.join(out_dir, "result.json")
    result = load(result_path) if os.path.isfile(result_path) else {}
    return proc.returncode, result, sorted(os.listdir(out_dir))


def baseline(case):
    """Naive single-table rule: one global mean/SD over the response column."""
    rows = case.get("readings") or []
    if not rows:
        return {"anomaly_rows": [], "shift": None, "saturated_count": 0}
    columns = [key for key in rows[0] if key.lower() not in TIME_LIKE]
    numeric = {}
    for column in columns:
        values = [number(row.get(column)) for row in rows]
        if all(value is not None for value in values):
            numeric[column] = values
    if not numeric:
        return {"anomaly_rows": [], "shift": None, "saturated_count": 0}
    preferred = [column for column in numeric
                 if column.lower() in ("value", "signal", "response", "y", "reading")]
    column = preferred[0] if preferred else list(numeric)[-1]
    values = numeric[column]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    sd = math.sqrt(variance)
    rows_out = [] if sd == 0 else [index + 1 for index, value in enumerate(values)
                                   if abs((value - mean) / sd) >= 3.0]
    return {"anomaly_rows": rows_out, "shift": None, "saturated_count": 0}


def shift_match(predicted, gold):
    if gold is None:
        return not predicted
    for item in predicted or []:
        if item.get("kind") != gold.get("kind"):
            continue
        if item.get("series") != gold.get("series"):
            continue
        if "first_row_after" in gold:
            after = item.get("rows_after") or []
            if not after or after[0] != gold["first_row_after"]:
                continue
        return True
    return False


def count_anomalies(predicted_rows, gold_rows):
    predicted = set(predicted_rows)
    gold = set(gold_rows)
    return {"tp": len(predicted & gold), "fp": len(predicted - gold),
            "fn": len(gold - predicted)}


def ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else 0.0


def score_side(cases, side):
    total = {"tp": 0, "fp": 0, "fn": 0}
    shift_hits = shift_total = 0
    saturation_hits = saturation_total = 0
    per_case = []
    for case, gold, payload in cases:
        counts = count_anomalies(payload["anomaly_rows"], gold["anomaly_rows"])
        for key in total:
            total[key] += counts[key]
        shift_ok = shift_match(payload.get("shift"), gold.get("shift"))
        shift_scored = gold.get("shift") is not None
        if shift_scored:
            shift_total += 1
            shift_hits += 1 if shift_ok else 0
        sat_scored = bool(gold.get("saturated_count", 0))
        sat_ok = payload.get("saturated_count") == gold.get("saturated_count", 0)
        if sat_scored:
            saturation_total += 1
            saturation_hits += 1 if sat_ok else 0
        per_case.append({
            "case_id": gold["case_id"],
            "anomalies": counts,
            "shift_ok": shift_ok if shift_scored else None,
            "saturation_ok": sat_ok if sat_scored else None,
        })
    precision = ratio(total["tp"], total["tp"] + total["fp"])
    recall = ratio(total["tp"], total["tp"] + total["fn"])
    f1 = 0.0 if not precision and not recall else round(
        2 * precision * recall / (precision + recall), 4)
    return {
        "anomaly": dict(total, precision=precision, recall=recall, f1=f1),
        "shift_cases_matched": "%d/%d" % (shift_hits, shift_total),
        "saturation_cases_matched": "%d/%d" % (saturation_hits, saturation_total),
        "unresolved_targets": total["fn"] + (shift_total - shift_hits) + (saturation_total - saturation_hits),
        "per_case": per_case,
        "side": side,
    }


def flag_text(value):
    if value is None:
        return "n/a"
    return "True" if value else "False"


def main():
    names = sorted(name for name in os.listdir(CASES) if name.endswith(".json"))
    prepared = []
    skill_rows = []
    baseline_rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for index, name in enumerate(names):
            case_path = os.path.join(CASES, name)
            gold_path = os.path.join(GOLD, name)
            if not os.path.isfile(gold_path):
                raise SystemExit("missing gold label: %s" % gold_path)
            case = load(case_path)
            gold = load(gold_path)
            code, result, files = run_skill(case_path, os.path.join(tmp, "case%d" % index))
            if code != 0 or result.get("status") not in ("success", "partial", "completed", "answered"):
                raise SystemExit("skill failed on %s (rc=%s, status=%s)" % (name, code, result.get("status")))
            predicted = {
                "anomaly_rows": [item.get("row") for item in result.get("anomalies") or []],
                "shift": (result.get("result") or {}).get("level_shifts") or [],
                "saturated_count": int(((result.get("result") or {}).get("data_quality") or {}).get("saturated_rows") or 0),
            }
            base = baseline(case)
            prepared.append((case, gold, predicted))
            skill_rows.append({"case_id": gold["case_id"], "payload": predicted, "files": files,
                               "claims": result.get("claims") or []})
            baseline_rows.append({"case_id": gold["case_id"], "payload": base})
    skill = score_side(prepared, "skill")
    base = score_side([(case, gold, row["payload"]) for (case, gold, _), row in zip(prepared, baseline_rows)], "baseline")
    claims_total = sum(len(row["claims"]) for row in skill_rows)
    claims_traced = sum(1 for row in skill_rows for claim in row["claims"] if claim.get("evidence"))
    artifacts = sorted({name for row in skill_rows for name in row["files"]})
    metrics = {
        "benchmark": "experimental-design/challenge-8354c69a result interpretation",
        "protocol": "same case files, same gold labels, one command per side; baseline = global mean/SD with |z|>=3, no grouping, no level-shift test, no range check",
        "skill": dict(skill, claims_total=claims_total, claims_with_evidence=claims_traced,
                      artifacts_per_run=len(artifacts), commands=1),
        "baseline": dict(base, claims_total=0, claims_with_evidence=0,
                         artifacts_per_run=0, commands=1),
        "delta": {
            "anomaly_f1": round(skill["anomaly"]["f1"] - base["anomaly"]["f1"], 4),
            "unresolved_targets": skill["unresolved_targets"] - base["unresolved_targets"],
            "traceable_claims": claims_traced,
        },
    }
    with open(os.path.join(HERE, "bench_metrics.json"), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    lines = ["# Bench — skill vs naive global threshold", "",
             "Protocol: identical case files and gold labels for both sides; the baseline is one global",
             "mean/SD filter (|z| >= 3) with no per-series grouping, no level-shift test and no range check.",
             "Gold labels: `bench/gold/*.json`; cases: `bench/cases/*.json`. Reproduce: `python bench/run_bench.py`.", "",
             "| metric | skill | baseline |", "|---|---|---|",
             "| anomaly TP / FP / FN | %d / %d / %d | %d / %d / %d |" % (
                 skill["anomaly"]["tp"], skill["anomaly"]["fp"], skill["anomaly"]["fn"],
                 base["anomaly"]["tp"], base["anomaly"]["fp"], base["anomaly"]["fn"]),
             "| anomaly precision | %s | %s |" % (skill["anomaly"]["precision"], base["anomaly"]["precision"]),
             "| anomaly recall | %s | %s |" % (skill["anomaly"]["recall"], base["anomaly"]["recall"]),
             "| anomaly F1 | %s | %s |" % (skill["anomaly"]["f1"], base["anomaly"]["f1"]),
             "| shift cases matched | %s | %s |" % (skill["shift_cases_matched"], base["shift_cases_matched"]),
             "| saturation cases matched | %s | %s |" % (skill["saturation_cases_matched"], base["saturation_cases_matched"]),
             "| unresolved gold targets | %d | %d |" % (skill["unresolved_targets"], base["unresolved_targets"]),
             "| claims with evidence pointer | %d / %d | 0 / 0 |" % (claims_traced, claims_total),
             "| artifacts written per run | %d | 0 |" % len(artifacts), "",
             "## Per case", "",
             "| case | anomaly TP/FP/FN | shift ok | saturation ok |",
             "|---|---|---|---|"]
    for item in skill["per_case"]:
        lines.append("| %s | %d/%d/%d | %s | %s |" % (
            item["case_id"], item["anomalies"]["tp"], item["anomalies"]["fp"],
            item["anomalies"]["fn"], flag_text(item["shift_ok"]), flag_text(item["saturation_ok"])))
    lines += ["", "## Baseline per case", "",
              "| case | anomaly TP/FP/FN | shift ok | saturation ok |",
              "|---|---|---|---|"]
    for item in base["per_case"]:
        lines.append("| %s | %d/%d/%d | %s | %s |" % (
            item["case_id"], item["anomalies"]["tp"], item["anomalies"]["fp"],
            item["anomalies"]["fn"], flag_text(item["shift_ok"]), flag_text(item["saturation_ok"])))
    lines += ["", "Interpretation: the gap comes from per-series robust statistics (median/MAD), the",
              "level-shift test and the declared-range check. The baseline misses the planted spike",
              "whenever between-batch offsets inflate the global variance, and it never reports a step",
              "or a saturation row. All numbers above are produced by this run, not asserted by hand.", ""]
    with open(os.path.join(HERE, "bench_report.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    print("\n".join(lines[:20]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
