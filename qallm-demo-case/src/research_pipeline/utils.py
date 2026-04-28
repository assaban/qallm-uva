import os
import json
import csv
import hashlib


def read_file(path):
    with open(path, "r") as f:
        return f.read()


def write_file(path, content):
    with open(path, "w") as f:
        f.write(content)


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def flatten_list(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            for sub in item:
                result.append(sub)
        else:
            result.append(item)
    return result


def deduplicate(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def format_percentage(value, total):
    if total == 0:
        return "0.00%"
    pct = value / total * 100
    return f"{pct:.2f}%"


def compute_hash(text):
    return hashlib.md5(text.encode()).hexdigest()


def merge_dicts(dict_a, dict_b):
    result = {}
    for k in dict_a:
        result[k] = dict_a[k]
    for k in dict_b:
        result[k] = dict_b[k]
    return result


def safe_divide(numerator, denominator, default=0.0):
    if denominator == 0:
        return default
    return numerator / denominator


def clamp(value, min_val, max_val):
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value


def moving_average(values, window=3):
    if len(values) < window:
        return values
    result = []
    for i in range(len(values) - window + 1):
        chunk = values[i : i + window]
        avg = sum(chunk) / len(chunk)
        result.append(avg)
    return result


def classify_severity(score):
    # Complex branching for severity classification
    if score >= 90:
        return "CRITICAL"
    elif score >= 75:
        return "HIGH"
    elif score >= 50:
        return "MEDIUM"
    elif score >= 25:
        return "LOW"
    elif score >= 10:
        return "INFO"
    else:
        return "NONE"


def generate_report(metrics, output_path):
    ensure_dir(os.path.dirname(output_path))

    report = {
        "summary": {},
        "details": [],
    }

    total = 0
    for name, value in metrics.items():
        total = total + value
        report["details"].append({"metric": name, "value": value})

    report["summary"]["total"] = total
    report["summary"]["count"] = len(metrics)
    report["summary"]["average"] = total / len(metrics) if metrics else 0

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    return report


def parse_csv_to_records(filepath):
    records = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)
    return records
