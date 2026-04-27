import os
import sys
import json

from research_pipeline.config import (
    DATA_DIR,
    OUTPUT_DIR,
    MODEL_TYPE,
    N_ESTIMATORS,
    MAX_DEPTH,
    TEST_SIZE,
    RANDOM_STATE,
)
from research_pipeline.data_loader import (
    load_csv,
    load_json,
    load_pickle,
    preprocess_tabular,
    normalize_features,
    split_data,
)
from research_pipeline.model import (
    train_decision_tree,
    predict,
    evaluate_model,
    save_model,
    complex_scoring,
)
from research_pipeline.utils import (
    ensure_dir,
    generate_report,
    format_percentage,
)


def run_pipeline(data_path, target_col, output_dir=None, normalize=True, evaluate=True):
    output_dir = output_dir or OUTPUT_DIR
    ensure_dir(output_dir)

    # Detect file format and load
    ext = os.path.splitext(data_path)[1].lower()
    if ext == ".csv":
        records = load_csv(data_path)
    elif ext == ".json":
        records = load_json(data_path)
    elif ext == ".pkl" or ext == ".pickle":
        records = load_pickle(data_path)
    else:
        print(f"Unsupported file format: {ext}")
        return None

    if not records:
        print("No records loaded.")
        return None

    # Preprocess
    features, labels = preprocess_tabular(records, target_col)

    if normalize:
        features = normalize_features(features)

    # Split
    X_train, X_test, y_train, y_test = split_data(features, labels, ratio=TEST_SIZE)

    if not X_train:
        print("Training set is empty after split.")
        return None

    # Train
    model = train_decision_tree(X_train, y_train, max_depth=MAX_DEPTH)

    # Save model
    model_path = os.path.join(output_dir, "model.json")
    save_model(model, model_path)

    results = {"model_path": model_path, "train_size": len(X_train), "test_size": len(X_test)}

    # Evaluate
    if evaluate and X_test:
        y_pred_train = predict(model, X_train)
        y_pred_test = predict(model, X_test)

        train_metrics = evaluate_model(y_train, y_pred_train)
        test_metrics = evaluate_model(y_test, y_pred_test)

        results["train_metrics"] = train_metrics
        results["test_metrics"] = test_metrics

        # Additional scoring
        for mode in ["accuracy", "precision", "recall", "f1", "mcc", "specificity"]:
            results[f"test_{mode}"] = complex_scoring(y_pred_test, y_test, mode)

        # Generate report
        report_metrics = {
            "train_accuracy": train_metrics["accuracy"],
            "test_accuracy": test_metrics["accuracy"],
            "test_precision": test_metrics["precision"],
            "test_recall": test_metrics["recall"],
            "test_f1": test_metrics["f1"],
        }
        report_path = os.path.join(output_dir, "report.json")
        generate_report(report_metrics, report_path)

        print(f"Train accuracy: {format_percentage(train_metrics['accuracy'], 1)}")
        print(f"Test accuracy:  {format_percentage(test_metrics['accuracy'], 1)}")
    else:
        print("Evaluation skipped.")

    # Save full results
    results_path = os.path.join(output_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python pipeline.py <data_path> <target_column>")
        sys.exit(1)

    data_file = sys.argv[1]
    target = sys.argv[2]
    run_pipeline(data_file, target)
