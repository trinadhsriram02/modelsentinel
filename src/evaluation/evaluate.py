"""
ModelSentinel Evaluation Framework

Runs the scanner against a labeled dataset of models
and computes classification metrics — Precision, Recall, F1.

Usage:
    python -m src.evaluation.evaluate

This creates test models, scans them, and measures how accurately
ModelSentinel identifies backdoored vs clean models.
"""

import os
import json
import time
from datetime import datetime

# ─────────────────────────────────────────
# Labeled test dataset — ground truth
# Each entry has the model type and the true label
# ─────────────────────────────────────────
TEST_CASES = [
    {
        "id": "eval_001",
        "model_type": "backdoored",
        "description": "ResNet18 with BadNets backdoor — class 0 target",
        "ground_truth": "BACKDOORED",
        "num_classes": 10
    },
    {
        "id": "eval_002",
        "model_type": "clean",
        "description": "ResNet18 with normal random initialization",
        "ground_truth": "CLEAN",
        "num_classes": 10
    },
    {
        "id": "eval_003",
        "model_type": "backdoored",
        "description": "ResNet18 with backdoor targeting class 5",
        "ground_truth": "BACKDOORED",
        "num_classes": 10
    },
    {
        "id": "eval_004",
        "model_type": "clean",
        "description": "ResNet18 clean — pretrained weights style",
        "ground_truth": "CLEAN",
        "num_classes": 10
    },
    {
        "id": "eval_005",
        "model_type": "backdoored",
        "description": "ResNet18 backdoored — extreme weight injection",
        "ground_truth": "BACKDOORED",
        "num_classes": 10
    }
]


def run_evaluation():
    """
    Run full evaluation pipeline:
    1. Create test models
    2. Scan each one
    3. Compare verdicts to ground truth
    4. Compute Precision, Recall, F1
    5. Print and save report
    """
    from src.scanner.model_loader import (
        create_backdoored_test_model,
        create_clean_test_model
    )
    from src.scanner.scanner_engine import scan_model

    print("=" * 60)
    print("ModelSentinel Evaluation Framework")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    os.makedirs("eval_models", exist_ok=True)

    y_true = []
    y_pred = []
    results = []
    total_time = 0

    for case in TEST_CASES:
        print(f"\n[{case['id']}] {case['description']}")
        print(f"  Ground truth: {case['ground_truth']}")

        # Create model
        path = f"eval_models/{case['id']}.pth"
        if case["model_type"] == "backdoored":
            create_backdoored_test_model(path, case["num_classes"])
        else:
            create_clean_test_model(path, case["num_classes"])

        # Scan model
        start = time.time()
        result = scan_model(path, case["id"], case["num_classes"])
        elapsed = round(time.time() - start, 2)
        total_time += elapsed

        verdict = result.get("verdict", "UNKNOWN")
        risk = result.get("risk_score", 0)

        print(f"  Predicted:    {verdict} (risk: {risk}/100)")
        print(f"  Time:         {elapsed}s")

        # Convert to binary for metrics
        # BACKDOORED or SUSPICIOUS = positive (1)
        # CLEAN = negative (0)
        y_true.append(1 if case["ground_truth"] == "BACKDOORED" else 0)
        y_pred.append(1 if verdict in ["BACKDOORED", "SUSPICIOUS"] else 0)

        correct = (
            (case["ground_truth"] == "BACKDOORED" and
             verdict in ["BACKDOORED", "SUSPICIOUS"]) or
            (case["ground_truth"] == "CLEAN" and verdict == "CLEAN")
        )
        print(f"  Correct:      {'✅ YES' if correct else '❌ NO'}")

        results.append({
            "id": case["id"],
            "ground_truth": case["ground_truth"],
            "predicted": verdict,
            "risk_score": risk,
            "correct": correct,
            "time_seconds": elapsed
        })

        # Clean up
        try:
            os.remove(path)
        except Exception:
            pass

    # ─── Compute metrics ─────────────────────────────────────

    print(f"\n{'=' * 60}")
    print("EVALUATION RESULTS")
    print(f"{'=' * 60}")

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0)
    accuracy = (tp + tn) / len(y_true) if y_true else 0
    avg_time = total_time / len(TEST_CASES)

    print(f"\nConfusion Matrix:")
    print(f"  True Positives  (backdoored, detected): {tp}")
    print(f"  True Negatives  (clean, cleared):       {tn}")
    print(f"  False Positives (clean, flagged):        {fp}")
    print(f"  False Negatives (backdoored, missed):   {fn}")

    print(f"\nClassification Metrics:")
    print(f"  Precision:  {precision:.2f}  "
          f"({int(precision*100)}% of detections are real threats)")
    print(f"  Recall:     {recall:.2f}  "
          f"(caught {int(recall*100)}% of all backdoored models)")
    print(f"  F1 Score:   {f1:.2f}  (balanced precision + recall)")
    print(f"  Accuracy:   {accuracy:.2f}  "
          f"(correct on {int(accuracy*100)}% of all cases)")

    print(f"\nPerformance:")
    print(f"  Average scan time: {avg_time:.1f}s per model")
    print(f"  Total eval time:   {total_time:.1f}s")

    # ─── Save report ─────────────────────────────────────────

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_models_tested": len(TEST_CASES),
        "metrics": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1_score": round(f1, 4),
            "accuracy": round(accuracy, 4)
        },
        "confusion_matrix": {
            "true_positives": tp,
            "true_negatives": tn,
            "false_positives": fp,
            "false_negatives": fn
        },
        "performance": {
            "avg_scan_time_seconds": round(avg_time, 2),
            "total_time_seconds": round(total_time, 2)
        },
        "individual_results": results
    }

    os.makedirs("src/evaluation", exist_ok=True)
    report_path = "src/evaluation/eval_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {report_path}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    run_evaluation()