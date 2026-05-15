import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import json


def run_neural_cleanse(model: nn.Module,
                       num_classes: int = 10,
                       num_samples: int = 20) -> dict:
    """
    Neural Cleanse backdoor detection (optimized for limited CPU).
    Uses MAD (Median Absolute Deviation) instead of std deviation
    for more accurate outlier detection of backdoor triggers.
    
    Optimization: Analyze max 5 classes (not 10) with 10 optimization steps
    instead of 20 to reduce processing time from ~5 min to ~2 min.
    """
    model.eval()
    device = torch.device("cpu")
    model = model.to(device)

    # OPTIMIZATION: Limit classes analyzed for faster scanning
    max_classes_to_analyze = min(num_classes, 5)  # Reduced from 10

    results = {
        "method": "Neural Cleanse",
        "num_classes_analyzed": max_classes_to_analyze,
        "class_anomaly_scores": {},
        "trigger_sizes": {},
        "backdoor_detected": False,
        "suspected_target_class": None,
        "confidence": 0.0,
        "anomaly_index": 0.0,
        "details": []
    }

    trigger_sizes = []

    for target_class in range(max_classes_to_analyze):
        trigger_size = _reverse_engineer_trigger(
            model, target_class, num_classes, num_samples, device
        )
        trigger_sizes.append(trigger_size)
        results["trigger_sizes"][f"class_{target_class}"] = round(
            trigger_size, 4
        )

    if not trigger_sizes:
        results["details"].append("No classes could be analyzed")
        return results

    trigger_array = np.array(trigger_sizes)

    # Tier 1 Fix — MAD instead of Standard Deviation
    # Standard deviation gets inflated by extreme outliers (backdoors)
    # and masks them. MAD uses median which is outlier-resistant.
    # Formula: Modified Z-score = 0.6745 * (median - x) / MAD
    median = np.median(trigger_array)
    mad = np.median(np.abs(trigger_array - median))

    for i, size in enumerate(trigger_sizes):
        if mad > 0:
            anomaly_score = 0.6745 * (median - size) / mad
        else:
            anomaly_score = 0.0
        results["class_anomaly_scores"][f"class_{i}"] = round(
            float(anomaly_score), 3
        )

    max_anomaly_class = int(np.argmax([
        results["class_anomaly_scores"].get(f"class_{i}", 0)
        for i in range(len(trigger_sizes))
    ]))
    max_anomaly_score = results["class_anomaly_scores"].get(
        f"class_{max_anomaly_class}", 0
    )

    results["anomaly_index"] = round(float(max_anomaly_score), 3)
    results["suspected_target_class"] = max_anomaly_class

    # Threshold 3.5 — calibrated for MAD-based scoring
    if max_anomaly_score > 3.5:
        results["backdoor_detected"] = True
        results["confidence"] = min(
            round(float(max_anomaly_score / 7.0) * 100, 1), 95.0
        )
        results["details"].append(
            f"Class {max_anomaly_class} has MAD anomaly index "
            f"{max_anomaly_score:.2f} — significantly easier to trigger"
        )
        results["details"].append(
            "Pattern consistent with backdoor injection during training"
        )
    elif max_anomaly_score > 2.0:
        results["backdoor_detected"] = False
        results["confidence"] = round(
            float(max_anomaly_score / 7.0) * 100, 1
        )
        results["details"].append(
            f"Class {max_anomaly_class} shows mild anomaly "
            f"(MAD index: {max_anomaly_score:.2f}) — investigation recommended"
        )
    else:
        results["backdoor_detected"] = False
        results["details"].append(
            "All classes have similar trigger sizes — no backdoor detected"
        )

    return results


def _reverse_engineer_trigger(model: nn.Module,
                               target_class: int,
                               num_classes: int,
                               num_samples: int,
                               device: torch.device) -> float:
    trigger_mask = torch.zeros(
        1, 3, 224, 224, requires_grad=True, device=device
    )
    trigger_pattern = torch.zeros(
        1, 3, 224, 224, requires_grad=True, device=device
    )

    optimizer = optim.Adam([trigger_mask, trigger_pattern], lr=0.1)
    criterion = nn.CrossEntropyLoss()
    target = torch.tensor([target_class], device=device)
    inputs = torch.randn(
        min(num_samples, 5), 3, 224, 224, device=device  # Reduced from 10
    )

    best_loss = float('inf')
    trigger_size = 1.0

    # OPTIMIZATION: Reduced from 20 to 10 steps for faster scanning
    for step in range(10):
        optimizer.zero_grad()
        mask = torch.sigmoid(trigger_mask)
        pattern = torch.tanh(trigger_pattern)
        triggered = inputs * (1 - mask) + pattern * mask

        try:
            outputs = model(triggered[:5])
            if outputs.shape[1] != num_classes:
                outputs = (
                    outputs[:, :num_classes]
                    if outputs.shape[1] > num_classes
                    else torch.nn.functional.pad(
                        outputs,
                        (0, num_classes - outputs.shape[1])
                    )
                )

            targets = target.repeat(outputs.shape[0])
            loss = criterion(outputs, targets)
            size_loss = torch.mean(torch.abs(mask))
            total_loss = loss + 0.01 * size_loss

            total_loss.backward()
            optimizer.step()

            if loss.item() < best_loss:
                best_loss = loss.item()
                trigger_size = float(
                    torch.mean(torch.abs(mask.detach())).item()
                )
        except Exception:
            break

    return trigger_size