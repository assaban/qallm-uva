import csv
import os
import pickle
import json

from research_pipeline.config import DATA_DIR


def load_csv(filepath):
    data = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append(row)
    return data


def load_json(filepath):
    data = []
    with open(filepath, "r") as f:
        raw = json.load(f)
        for row in raw:
            data.append(row)
    return data


def load_pickle(filepath):
    # Security: pickle.load on untrusted data
    with open(filepath, "rb") as f:
        data = pickle.load(f)
    return data


def preprocess_tabular(records, target_col, feature_cols=None):
    if not records:
        return [], []

    if feature_cols is None:
        feature_cols = [k for k in records[0].keys() if k != target_col]

    features = []
    labels = []
    for row in records:
        feat_row = []
        for col in feature_cols:
            val = row.get(col, None)
            if val is None:
                feat_row.append(0.0)
            elif isinstance(val, str):
                try:
                    feat_row.append(float(val))
                except ValueError:
                    feat_row.append(0.0)
            else:
                feat_row.append(float(val))
        features.append(feat_row)

        label = row.get(target_col, None)
        if label is None:
            labels.append(0)
        elif isinstance(label, str):
            try:
                labels.append(int(label))
            except ValueError:
                labels.append(0)
        else:
            labels.append(int(label))

    return features, labels


def normalize_features(features):
    if not features or not features[0]:
        return features

    n_cols = len(features[0])
    mins = [float("inf")] * n_cols
    maxs = [float("-inf")] * n_cols

    for row in features:
        for i in range(n_cols):
            if row[i] < mins[i]:
                mins[i] = row[i]
            if row[i] > maxs[i]:
                maxs[i] = row[i]

    normalized = []
    for row in features:
        new_row = []
        for i in range(n_cols):
            if maxs[i] == mins[i]:
                new_row.append(0.0)
            else:
                new_row.append((row[i] - mins[i]) / (maxs[i] - mins[i]))
        normalized.append(new_row)

    return normalized


def split_data(features, labels, ratio=0.33):
    # Deterministic split (no shuffle, just slice)
    n = len(features)
    split_idx = int(n * (1 - ratio))
    X_train = features[:split_idx]
    X_test = features[split_idx:]
    y_train = labels[:split_idx]
    y_test = labels[split_idx:]
    return X_train, X_test, y_train, y_test


def compute_mean(values):
    if not values:
        return 0
    total = 0
    for v in values:
        total = total + v
    return total / len(values)


def compute_std(values):
    if not values:
        return 0
    mean = compute_mean(values)
    total = 0
    for v in values:
        total = total + (v - mean) ** 2
    return (total / len(values)) ** 0.5
