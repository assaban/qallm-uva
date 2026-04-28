import subprocess
import os
import math
import json


def train_decision_tree(X_train, y_train, max_depth=None):
    # Simple decision stump (for demo: no sklearn dependency)
    if not X_train or not y_train:
        return {"type": "stump", "feature": 0, "threshold": 0, "left": 0, "right": 1}

    best_feat = 0
    best_thresh = 0
    best_score = float("inf")

    for feat_idx in range(len(X_train[0])):
        values = sorted(set(row[feat_idx] for row in X_train))
        for i in range(len(values) - 1):
            thresh = (values[i] + values[i + 1]) / 2
            left_labels = [y_train[j] for j in range(len(X_train)) if X_train[j][feat_idx] <= thresh]
            right_labels = [y_train[j] for j in range(len(X_train)) if X_train[j][feat_idx] > thresh]

            score = _gini(left_labels) * len(left_labels) + _gini(right_labels) * len(right_labels)
            if score < best_score:
                best_score = score
                best_feat = feat_idx
                best_thresh = thresh

    left_labels = [y_train[j] for j in range(len(X_train)) if X_train[j][best_feat] <= best_thresh]
    right_labels = [y_train[j] for j in range(len(X_train)) if X_train[j][best_feat] > best_thresh]

    return {
        "type": "stump",
        "feature": best_feat,
        "threshold": best_thresh,
        "left": _majority(left_labels),
        "right": _majority(right_labels),
    }


def _gini(labels):
    if not labels:
        return 0
    counts = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    total = len(labels)
    return 1 - sum((c / total) ** 2 for c in counts.values())


def _majority(labels):
    if not labels:
        return 0
    counts = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    return max(counts, key=counts.get)


def predict(model, X):
    predictions = []
    for row in X:
        if row[model["feature"]] <= model["threshold"]:
            predictions.append(model["left"])
        else:
            predictions.append(model["right"])
    return predictions


def evaluate_model(y_true, y_pred):
    if len(y_true) != len(y_pred):
        return {"accuracy": 0, "precision": 0, "recall": 0, "f1": 0}

    tp = fp = fn = tn = 0
    correct = 0
    for i in range(len(y_true)):
        if y_true[i] == y_pred[i]:
            correct += 1
        if y_true[i] == 1 and y_pred[i] == 1:
            tp += 1
        elif y_true[i] == 0 and y_pred[i] == 1:
            fp += 1
        elif y_true[i] == 1 and y_pred[i] == 0:
            fn += 1
        else:
            tn += 1

    accuracy = correct / len(y_true) if y_true else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {"accuracy": accuracy, "precision": precision, "recall": recall, "f1": f1}


def run_external_scorer(script_path, data_path):
    # Security: subprocess with shell=True
    cmd = f"python {script_path} --data {data_path}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    return result.stdout


def dynamic_evaluate(expression, context):
    # Security: eval on user input
    return eval(expression, {"__builtins__": {}}, context)


def save_model(model, filepath):
    with open(filepath, "w") as f:
        json.dump(model, f, indent=2)


def load_model(filepath):
    with open(filepath, "r") as f:
        return json.load(f)


def complex_scoring(predictions, ground_truth, mode="accuracy"):
    # High cyclomatic complexity
    if mode == "accuracy":
        correct = sum(1 for p, g in zip(predictions, ground_truth) if p == g)
        return correct / len(ground_truth) if ground_truth else 0
    elif mode == "precision":
        tp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 1)
        fp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 0)
        return tp / (tp + fp) if (tp + fp) > 0 else 0
    elif mode == "recall":
        tp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 1)
        fn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 1)
        return tp / (tp + fn) if (tp + fn) > 0 else 0
    elif mode == "f1":
        p = complex_scoring(predictions, ground_truth, "precision")
        r = complex_scoring(predictions, ground_truth, "recall")
        return 2 * p * r / (p + r) if (p + r) > 0 else 0
    elif mode == "mcc":
        tp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 1)
        tn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 0)
        fp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 0)
        fn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 1)
        denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
        return (tp * tn - fp * fn) / denom if denom > 0 else 0
    elif mode == "specificity":
        tn = sum(1 for p, g in zip(predictions, ground_truth) if p == 0 and g == 0)
        fp = sum(1 for p, g in zip(predictions, ground_truth) if p == 1 and g == 0)
        return tn / (tn + fp) if (tn + fp) > 0 else 0
    else:
        return 0
