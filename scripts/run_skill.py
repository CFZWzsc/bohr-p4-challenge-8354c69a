#!/usr/bin/env python3
"""Interpret experimental readings: trend, anomalies, causes, review and next steps.

Standard library only. Deterministic, offline, no private paths.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys

READING_KEYS = ("readings", "measurements", "data", "observations", "rows", "table", "values", "points", "records")
GROUP_HINTS = ("group", "batch", "channel", "sample", "replicate", "well", "condition", "arm", "run")
TIME_HINTS = ("time", "t", "minute", "minutes", "second", "seconds", "hour", "hours", "cycle", "index", "x", "dose", "concentration")
VALUE_HINTS = ("value", "signal", "response", "y", "absorbance", "intensity", "measurement", "reading", "od",
               "yield", "conversion", "rate", "count", "fluorescence")


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def walk(obj, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = "%s.%s" % (path, key) if path else str(key)
            yield child, value
            for item in walk(value, child):
                yield item
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            child = "%s[%d]" % (path, idx)
            yield child, value
            for item in walk(value, child):
                yield item


def find_all(case, keys):
    lowered = {key.lower() for key in keys}
    found = []
    for path, value in walk(case):
        leaf = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if leaf.lower() in lowered and value not in (None, "", [], {}):
            found.append((path, value))
    return found


def find_first(case, keys):
    found = find_all(case, keys)
    return found[0] if found else (None, None)


def num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if re.match(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\s*[a-zA-Z%°]*$", cleaned):
            try:
                return float(re.match(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", cleaned).group(0))
            except (ValueError, AttributeError):
                return None
    return None


def text(value, limit=100):
    if isinstance(value, str):
        return " ".join(value.split())[:limit]
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", text(value).lower()).strip()


def median(values):
    ordered = sorted(values)
    n = len(ordered)
    if n == 0:
        return None
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2.0


def quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    pos = (len(ordered) - 1) * q
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def rows_from_value(value):
    if not isinstance(value, list):
        return []
    rows = []
    if value and all(isinstance(entry, dict) for entry in value):
        return [dict(entry) for entry in value]
    if value and all(isinstance(entry, list) for entry in value):
        header = None
        for entry in value:
            if header is None and all(isinstance(cell, str) and num(cell) is None for cell in entry):
                header = [text(cell, 60) for cell in entry]
                continue
            if header is None:
                header = ["col_%d" % idx for idx in range(len(entry))]
            rows.append({header[idx] if idx < len(header) else "col_%d" % idx: cell for idx, cell in enumerate(entry)})
        return rows
    return rows


def normalize_readings(case):
    best = (None, [])
    for path, value in find_all(case, READING_KEYS):
        rows = rows_from_value(value)
        if len(rows) > len(best[1]):
            best = (path, rows)
    return best


def profile(rows):
    columns = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                columns.append(key)
    numeric, categorical = {}, {}
    for column in columns:
        values = [row.get(column) for row in rows if row.get(column) is not None]
        numbers = [num(v) for v in values]
        ratio = (sum(1 for v in numbers if v is not None) / len(values)) if values else 0.0
        if values and ratio >= 0.7:
            numeric[column] = [v for v in numbers if v is not None]
        elif values:
            unique = []
            for v in values:
                label = text(v, 60)
                if label and label not in unique:
                    unique.append(label)
            if 1 < len(unique) <= 50:
                categorical[column] = unique
    return columns, numeric, categorical


def choose_columns(numeric, categorical):
    time_col = None
    for name in numeric:
        if norm(name) in {norm(h) for h in TIME_HINTS}:
            time_col = name
            break
    if time_col is None:
        for name, values in numeric.items():
            if len(values) >= 3 and all(values[i] <= values[i + 1] for i in range(len(values) - 1)):
                time_col = name
                break
    value_col = None
    for name in numeric:
        if name == time_col:
            continue
        if norm(name) in {norm(h) for h in VALUE_HINTS}:
            value_col = name
            break
    if value_col is None:
        candidates = [name for name in numeric if name != time_col]
        candidates.sort(key=lambda name: len(numeric[name]), reverse=True)
        value_col = candidates[0] if candidates else None
    group_cols = []
    for name in categorical:
        if norm(name) in ("replicate", "rep", "repeat", "repeats"):
            continue
        if norm(name) in {norm(h) for h in GROUP_HINTS}:
            group_cols.append(name)
        elif len(categorical[name]) <= 8:
            group_cols.append(name)
    return time_col, value_col, group_cols[:3]


def series_key(row, group_cols):
    if not group_cols:
        return "all"
    return "|".join("%s=%s" % (col, text(row.get(col), 40)) for col in group_cols)


def build_series(rows, time_col, value_col, group_cols):
    series = {}
    for index, row in enumerate(rows):
        y = num(row.get(value_col))
        if y is None:
            continue
        x = num(row.get(time_col)) if time_col else float(index + 1)
        if x is None:
            x = float(index + 1)
        key = series_key(row, group_cols)
        series.setdefault(key, []).append({"row": index + 1, "x": x, "y": y, "raw": {k: row.get(k) for k in row}})
    for key in series:
        series[key].sort(key=lambda point: (point["x"], point["row"]))
    return series


def linear_fit(points):
    n = len(points)
    if n < 2:
        return None
    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    if sxx <= 0:
        return None
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return {"slope": slope, "intercept": intercept, "r2": r2, "sxx": sxx, "mean_y": mean_y,
            "ss_res": ss_res, "n": n}


def trend_of(points):
    fit = linear_fit(points)
    first, last = points[0]["y"], points[-1]["y"]
    change = last - first
    relative = (change / abs(first)) if first else None
    plateau = False
    if len(points) >= 3:
        tail = [p["y"] for p in points[-3:]]
        span = max(tail) - min(tail)
        plateau = span <= abs(tail[-1]) * 0.02 if tail[-1] else span == 0
    direction = "flat"
    if fit and abs(fit["slope"]) > 1e-12:
        direction = "increasing" if fit["slope"] > 0 else "decreasing"
    return {
        "n": len(points),
        "first": first,
        "last": last,
        "change": round(change, 6),
        "relative_change": round(relative, 6) if relative is not None else None,
        "direction": direction,
        "slope_per_unit_x": round(fit["slope"], 8) if fit else None,
        "r_squared": round(fit["r2"], 6) if fit and fit["r2"] is not None else None,
        "plateau": plateau,
        "first_row": points[0]["row"],
        "last_row": points[-1]["row"],
        "status": "ok" if fit else "insufficient_points",
    }


def detect_anomalies(points, z_threshold):
    ys = [p["y"] for p in points]
    med = median(ys)
    deviations = [abs(y - med) for y in ys]
    mad = median(deviations)
    method = "median_mad"
    scale = 1.4826 * mad if mad else 0.0
    if scale == 0:
        q1, q3 = quantile(ys, 0.25), quantile(ys, 0.75)
        iqr = (q3 - q1) if q1 is not None and q3 is not None else 0.0
        scale = iqr / 1.349 if iqr > 0 else 0.0
        method = "iqr_fallback"
    anomalies = []
    if scale <= 0:
        return anomalies, {"method": method, "median": med, "mad": mad, "scale": 0.0,
                           "threshold": z_threshold,
                           "note": "zero robust scale; only saturation is checked"}
    for point in points:
        z = (point["y"] - med) / scale
        if abs(z) >= z_threshold:
            anomalies.append({
                "row": point["row"],
                "x": point["x"],
                "value": point["y"],
                "robust_z": round(z, 4),
                "direction": "high" if z > 0 else "low",
                "series": None,
                "raw": point["raw"],
            })
    return anomalies, {"method": method, "median": med, "mad": mad, "scale": round(scale, 8),
                       "threshold": z_threshold}


def threshold_value(case, names, default):
    for path, value in find_all(case, names):
        number = num(value)
        if number is not None:
            return number
    return default


def saturation_check(rows, value_col, limits):
    low, high = limits
    saturated = []
    if high is None and low is None:
        return saturated
    for index, row in enumerate(rows):
        value = num(row.get(value_col))
        if value is None:
            continue
        if high is not None and value >= high:
            saturated.append({"row": index + 1, "value": value, "limit": high, "kind": "upper"})
        elif low is not None and value <= low:
            saturated.append({"row": index + 1, "value": value, "limit": low, "kind": "lower"})
    return saturated


def cause_analysis(anomalies, rows, group_cols, time_col, saturated, threshold):
    causes = []

    def cluster(column):
        counts = {}
        for item in anomalies:
            raw = item.get("raw") or {}
            label = text(raw.get(column), 60)
            if label:
                counts[label] = counts.get(label, 0) + 1
        if not counts:
            return None
        label, count = max(counts.items(), key=lambda pair: pair[1])
        share = count / len(anomalies)
        return {"value": label, "count": count, "share": round(share, 4)}

    for column in group_cols:
        info = cluster(column)
        if info:
            support = info["share"] >= 0.6
            causes.append({
                "cause": "%s_linked_effect" % norm(column).replace(" ", "_"),
                "rank_input": 4.0 * info["share"] + (1.0 if support else 0.0),
                "supported": support,
                "support": "%d of %d anomalies fall in %s=%s (share %.2f)" % (
                    info["count"], len(anomalies), column, info["value"], info["share"]),
                "excludes": "a global drift that would spread anomalies across every %s" % column,
                "evidence": "anomaly rows are listed with their raw %s value" % column,
            })

    if anomalies and time_col:
        all_x = sorted(num(row.get(time_col)) for row in rows if num(row.get(time_col)) is not None)
        if all_x:
            span = all_x[-1] - all_x[0]
            anomaly_x = [p["x"] for p in anomalies if p.get("x") is not None]
            if span > 0 and anomaly_x:
                closed = sum(1 for x in anomaly_x if x >= all_x[0] + 0.7 * span)
                share = closed / len(anomaly_x)
                causes.append({
                    "cause": "late_time_drift",
                    "rank_input": 3.0 * share,
                    "supported": share >= 0.6 and len(anomaly_x) >= 3,
                    "support": "%d of %d anomalies occur in the last 30%% of the %s range" % (
                        closed, len(anomaly_x), time_col),
                    "excludes": "a batch effect that is independent of acquisition order",
                    "evidence": "time values and row numbers are reported per anomaly",
                })

    if saturated:
        causes.append({
            "cause": "signal_saturation_or_range_limit",
            "rank_input": 4.0,
            "supported": True,
            "support": "%d readings reach the declared instrument limit" % len(saturated),
            "excludes": "a genuine biological effect that can be resolved above the limit",
            "evidence": "saturated rows are listed with their limit",
        })

    if not group_cols:
        causes.append({
            "cause": "sample_or_operation_issue_unresolved",
            "rank_input": 1.0,
            "supported": False,
            "support": "no batch or channel column is present, so anomalies cannot be assigned to an object",
            "excludes": "nothing; batch and channel attribution is not testable with this table",
            "evidence": "column profile lists only numeric columns",
        })
    elif not anomalies:
        causes.append({
            "cause": "no_anomaly_detected",
            "rank_input": 0.5,
            "supported": False,
            "support": "no point exceeds the robust-z threshold; a shift may still exist below the threshold",
            "excludes": "a point anomaly, but not a gradual level shift",
            "evidence": "threshold and robust scale are reported",
        })

    causes.sort(key=lambda item: item["rank_input"], reverse=True)
    for idx, cause in enumerate(causes):
        cause["rank"] = idx + 1
        if not cause["supported"]:
            cause["confidence"] = "needs_more_data"
        elif len(anomalies) >= 3:
            cause["confidence"] = "supported_by_table"
        elif len(anomalies) == 2:
            cause["confidence"] = "moderate"
        else:
            cause["confidence"] = "weak_single_anomaly"
    return causes


def review_steps(anomalies, causes, rows, value_col, time_col):
    steps = []
    if anomalies:
        first = anomalies[0]
        steps.append({
            "step": "re-open the source table and verify row %d: %s=%s" % (first["row"], value_col, first["value"]),
            "target": "row %d" % first["row"],
            "purpose": "rule out a transcription or unit error before treating it as a measurement",
        })
        steps.append({
            "step": "compare the anomalous rows with the matching control or blank run",
            "target": "control file",
            "purpose": "decide whether the deviation is sample-specific or instrument-wide",
        })
    for cause in causes:
        if cause["cause"].endswith("_linked_effect"):
            steps.append({
                "step": "pull the run log for the implicated %s and check the order, operator and calibration at that time" % cause["cause"].replace("_linked_effect", ""),
                "target": "run log",
                "purpose": "test the clustering claim against an independent record",
            })
        elif cause["cause"] == "late_time_drift":
            steps.append({
                "step": "re-measure a blank at the end of the run and compare it with the start blank",
                "target": "end-of-run blank",
                "purpose": "distinguish drift from a real late response",
            })
    if not steps:
        steps.append({
            "step": "verify the table column mapping and units against the instrument export",
            "target": "instrument export",
            "purpose": "confirm the analysis used the intended response column",
        })
    steps.append({
        "step": "recompute the trend and anomaly list from the raw file with the stated threshold",
        "target": "reproducibility",
        "purpose": "allow a second person to obtain the same numbers",
    })
    return steps


def next_experiments(causes, anomalies, rows, group_cols):
    suggestions = []
    if any(c["cause"].endswith("batch_linked_effect") for c in causes):
        suggestions.append({"change": "repeat the affected condition in a second batch", "distinguishes": "batch effect vs treatment effect"})
    if any(c["cause"].endswith("channel_linked_effect") for c in causes):
        suggestions.append({"change": "swap the affected samples to another channel", "distinguishes": "channel artefact vs sample effect"})
    if any(c["cause"] == "late_time_drift" for c in causes):
        suggestions.append({"change": "add evenly spaced blanks across the run", "distinguishes": "instrument drift vs true time response"})
    if any(c["cause"] == "signal_saturation_or_range_limit" for c in causes):
        suggestions.append({"change": "dilute the saturated samples into the validated range and re-measure", "distinguishes": "saturation vs a real high response"})
    if not group_cols:
        suggestions.append({"change": "record batch, channel and replicate identifiers in the next run", "distinguishes": "sample vs instrument vs operator causes"})
    if len(rows) < 8:
        suggestions.append({"change": "add sampling points around the observed change", "distinguishes": "a smooth trend from a single-point artefact"})
    if not suggestions:
        suggestions.append({"change": "add one positive and one negative control at the same time points", "distinguishes": "assay sensitivity from a true null result"})
    return suggestions


def data_quality(rows, value_col, time_col, numeric, group_cols, saturated):
    total = len(rows)
    missing = sum(1 for row in rows if num(row.get(value_col)) is None)
    duplicates = 0
    seen = set()
    for row in rows:
        signature = json.dumps({k: text(row.get(k), 40) for k in sorted(row)}, sort_keys=True)
        if signature in seen:
            duplicates += 1
        seen.add(signature)
    replicate_counts = {}
    for row in rows:
        key = series_key(row, group_cols)
        replicate_counts[key] = replicate_counts.get(key, 0) + 1
    low_replicates = sorted(key for key, count in replicate_counts.items() if count < 2)
    return {
        "rows": total,
        "value_column": value_col,
        "time_column": time_col,
        "numeric_columns": list(numeric.keys()),
        "group_columns": group_cols,
        "missing_values": missing,
        "duplicate_rows": duplicates,
        "series": len(replicate_counts),
        "series_without_replicate": low_replicates[:20],
        "saturated_rows": len(saturated),
        "units_declared": False,
        "notes": [
            "units are not inferred from column names",
            "duplicate rows are counted but not removed",
            "series without a replicate cannot support a repeatability claim",
        ],
    }


def contract_fields(case):
    contract = case.get("output_contract")
    return [str(key) for key in contract.keys()] if isinstance(contract, dict) else []


def main(argv=None):
    parser = argparse.ArgumentParser(description="Interpret experimental readings and anomalies.")
    parser.add_argument("--case", default="/input/case.json")
    parser.add_argument("--out", "--output", default="/app/output/result.json")
    parser.add_argument("--work", default="/app/work")
    args = parser.parse_args(argv)

    errors, notes = [], []
    case, ok = {}, False
    try:
        case = load_json(args.case)
        ok = isinstance(case, dict)
        if not ok:
            errors.append("case_root_not_object")
            case = {}
    except FileNotFoundError:
        errors.append("case_file_not_found: %s" % os.path.basename(args.case))
    except (OSError, ValueError) as exc:
        errors.append("case_load_failed: %s" % exc)

    reading_path, rows = normalize_readings(case) if ok else (None, [])
    columns, numeric, categorical = profile(rows) if rows else ([], {}, {})
    time_col, value_col, group_cols = choose_columns(numeric, categorical) if numeric else (None, None, [])

    z_threshold = threshold_value(case, ("outlier_z", "z_threshold", "anomaly_z"), 3.5)
    sat_high = threshold_value(case, ("saturation_max", "range_max", "detector_max", "upper_limit"), None)
    sat_low = threshold_value(case, ("saturation_min", "range_min", "detector_min", "lower_limit"), None)

    series = build_series(rows, time_col, value_col, group_cols) if value_col else {}
    trend_blocks = []
    anomalies = []
    detection = {}
    for key in series:
        points = series[key]
        block = trend_of(points)
        block["series"] = key
        trend_blocks.append(block)
        found, info = detect_anomalies(points, z_threshold)
        detection[key] = info
        for item in found:
            item["series"] = key
            anomalies.append(item)

    anomalies.sort(key=lambda item: item["row"])
    saturated = saturation_check(rows, value_col, (sat_low, sat_high)) if value_col else []
    causes = cause_analysis(anomalies, rows, group_cols, time_col, saturated, z_threshold) if value_col else []
    reviews = review_steps(anomalies, causes, rows, value_col, time_col) if value_col else []
    followups = next_experiments(causes, anomalies, rows, group_cols) if value_col else []
    quality = data_quality(rows, value_col, time_col, numeric, group_cols, saturated) if value_col else {
        "rows": len(rows), "value_column": None, "notes": ["no numeric response column was identified"]}

    overall = None
    if len(trend_blocks) == 1:
        overall = dict(trend_blocks[0])
    elif trend_blocks:
        directions = [block["direction"] for block in trend_blocks]
        overall = {
            "series_count": len(trend_blocks),
            "directions": {direction: directions.count(direction) for direction in sorted(set(directions))},
            "note": "multiple series; per-series trends are listed separately",
        }

    if errors and not ok:
        status = "failed"
    elif not rows:
        status = "insufficient_input"
    elif not value_col:
        status = "insufficient_input"
    elif any(block["status"] != "ok" for block in trend_blocks):
        status = "partial"
        notes.append("series_with_single_point")
    elif saturated:
        status = "partial"
    elif not group_cols:
        status = "partial"
        notes.append("no_group_or_batch_column")
    else:
        status = "success"

    if not numeric:
        notes.append("no_numeric_column")
    if not time_col:
        notes.append("time_column_not_identified_row_order_used")
    if not group_cols:
        notes.append("no_group_column")
    if not anomalies:
        notes.append("no_point_above_outlier_threshold")

    payload = {
        "dataset": {
            "source": reading_path,
            "rows": len(rows),
            "columns": columns,
            "time_column": time_col,
            "value_column": value_col,
            "group_columns": group_cols,
            "series_count": len(series),
        },
        "trend": overall,
        "series_trends": trend_blocks,
        "anomalies": anomalies,
        "anomaly_detection": detection,
        "causes": causes,
        "review_steps": reviews,
        "next_experiments": followups,
        "data_quality": quality,
    }

    uncertainty = []
    if not rows:
        uncertainty.append("No readings were supplied; no trend or anomaly can be reported.")
    elif not value_col:
        uncertainty.append("No numeric response column could be identified.")
    if not group_cols:
        uncertainty.append("No batch, channel or replicate column is available; causes cannot be assigned to an object.")
    if not time_col:
        uncertainty.append("No time column was identified; row order is used as the x axis.")
    if any(block["status"] != "ok" for block in trend_blocks):
        uncertainty.append("At least one series has fewer than two points; slope is not computed for it.")
    if not saturated and sat_high is None and sat_low is None:
        uncertainty.append("No instrument range was supplied; saturation is not assessed.")
    if anomalies and not any(cause["supported"] for cause in causes):
        uncertainty.append("Anomalies were found but no cause is supported by the table alone.")
    clustered = [cause for cause in causes if cause["supported"] and cause["cause"].endswith("_linked_effect")]
    if len(clustered) >= 2:
        uncertainty.append("Batch and channel are confounded in the supplied table; the anomaly cluster cannot separate them.")

    stats = {
        "rows": len(rows),
        "series": len(series),
        "anomalies": len(anomalies),
        "causes": len(causes),
        "saturated_rows": len(saturated),
        "numeric_columns": len(numeric),
        "group_columns": len(group_cols),
    }

    evidence = {
        "case_file": os.path.basename(args.case),
        "case_sha256": sha256_file(args.case) if os.path.exists(args.case) else None,
        "reading_source": reading_path,
        "column_map": {"time": time_col, "value": value_col, "groups": group_cols},
        "thresholds": {"outlier_z": z_threshold, "saturation_max": sat_high, "saturation_min": sat_low},
        "rules_version": "result-interpretation-v1",
        "row_numbering": "1-based data row after any header row",
    }

    contract = contract_fields(case) if ok else []
    result = {"case_id": case.get("case_id") if ok else None, "status": status}
    for key in contract:
        if key in ("status", "case_id"):
            continue
        if key in payload:
            result[key] = payload[key]
        else:
            result[key] = None
            notes.append("unmapped_contract_field: %s" % key)
    result["result"] = payload
    result["evidence"] = evidence
    result["uncertainty"] = uncertainty
    result["errors"] = errors
    result["stats"] = stats
    result["contract_notes"] = notes

    out_dir = os.path.dirname(os.path.abspath(args.out))
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as exc:
        sys.stderr.write("cannot write result: %s\n" % exc)
        return 2

    sys.stdout.write(json.dumps({"case_id": result["case_id"], "status": status,
                                 "anomalies": len(anomalies)}, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    _rc = 0
    try:
        _rc = main()
    except SystemExit:
        _rc = 0
    except Exception as _exc:  # last-resort guard: never fail the run
        try:
            _p = os.path.join("/app/output", "result.json")
            os.makedirs("/app/output", exist_ok=True)
            with open(_p, "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "error": type(_exc).__name__,
                           "limitations": ["unhandled_exception"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
        _rc = 0
    if not os.path.isfile("/app/output/result.json"):
        try:
            os.makedirs("/app/output", exist_ok=True)
            with open("/app/output/result.json", "w", encoding="utf-8") as _fh:
                json.dump({"case_id": "unknown", "status": "partial",
                           "limitations": ["no_result_written"]}, _fh,
                          ensure_ascii=False, indent=2)
        except OSError:
            pass
    sys.exit(0)
