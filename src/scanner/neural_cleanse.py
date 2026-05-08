import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from torchvision import transforms
import json


def run_neural_cleanse(model: nn.Module,
                       num_classes: int = 10,
                       num_samples: int = 20) -> dict:
    """
    Neural Cleanse backdoor detection algorithm.

    How it works:
    For each class, we try to find the smallest trigger pattern that
    causes the model to classify any input as that class.
    If one class requires an unusually small trigger, that class is
    likely the backdoor target — it has been made easy to activate.

    Returns anomaly index scores for each class.
    High anomaly index = likely backdoor target.
    """
    model.eval()
    device = torch.device("cpu")
    model = model.to(device)

    results = {
        "method": "Neural Cleanse",
        "num_classes_analyzed": num_classes,
        "class_anomaly_scores": {},
        "trigger_sizes": {},
        "backdoor_detected": False,
        "suspected_target_class": None,
        "confidence": 0.0,
        "anomaly_index": 0.0,
        "details": []
    }

    trigger_sizes = []

    for target_class in range(min(num_classes, 10)):
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
    mean_size = np.mean(trigger_array)
    std_size = np.std(trigger_array)

    # Anomaly index: how many std deviations below mean
    # A backdoored class has a much smaller trigger than average
    for i, size in enumerate(trigger_sizes):
        if std_size > 0:
            anomaly_score = (mean_size - size) / std_size
        else:
            anomaly_score = 0.0
        results["class_anomaly_scores"][f"class_{i}"] = round(
            float(anomaly_score), 3
        )

    # Find the most anomalous class
    max_anomaly_class = int(np.argmax([
        results["class_anomaly_scores"].get(f"class_{i}", 0)
        for i in range(len(trigger_sizes))
    ]))
    max_anomaly_score = results["class_anomaly_scores"].get(
        f"class_{max_anomaly_class}", 0
    )

    results["anomaly_index"] = round(float(max_anomaly_score), 3)
    results["suspected_target_class"] = max_anomaly_class

    # Threshold: anomaly index > 2.0 indicates backdoor
    # (standard deviation based detection)
    if max_anomaly_score > 2.0:
        results["backdoor_detected"] = True
        results["confidence"] = min(
            round(float(max_anomaly_score / 5.0) * 100, 1), 95.0
        )
        results["details"].append(
            f"Class {max_anomaly_class} has anomaly index "
            f"{max_anomaly_score:.2f} — significantly easier to "
            f"trigger than other classes"
        )
        results["details"].append(
            "This pattern is consistent with backdoor injection "
            "during training"
        )
    elif max_anomaly_score > 1.5:
        results["backdoor_detected"] = False
        results["confidence"] = round(float(max_anomaly_score / 5.0) * 100, 1)
        results["details"].append(
            f"Class {max_anomaly_class} shows mild anomaly "
            f"(index: {max_anomaly_score:.2f}) — further investigation recommended"
        )
    else:
        results["backdoor_detected"] = False
        results["details"].append(
            "All classes have similar trigger sizes — "
            "no backdoor pattern detected"
        )

    return results


def _reverse_engineer_trigger(model: nn.Module,
                               target_class: int,
                               num_classes: int,
                               num_samples: int,
                               device: torch.device) -> float:
    """
    Reverse engineer the smallest trigger for a target class.
    Uses gradient-based optimization to find the minimal perturbation.
    """
    # Start with a random trigger mask and pattern
    trigger_mask = torch.zeros(1, 3, 224, 224,
                               requires_grad=True, device=device)
    trigger_pattern = torch.zeros(1, 3, 224, 224,
                                  requires_grad=True, device=device)

    optimizer = optim.Adam([trigger_mask, trigger_pattern],
                           lr=0.1)
    criterion = nn.CrossEntropyLoss()
    target = torch.tensor([target_class], device=device)

    # Generate synthetic input samples
    inputs = torch.randn(min(num_samples, 20), 3, 224, 224,
                         device=device)

    best_loss = float('inf')
    trigger_size = 1.0

    for step in range(20):
        optimizer.zero_grad()

        # Apply trigger to inputs
        mask = torch.sigmoid(trigger_mask)
        pattern = torch.tanh(trigger_pattern)
        triggered = inputs * (1 - mask) + pattern * mask

        # Forward pass
        try:
            outputs = model(triggered[:5])

            # Ensure output has correct number of classes
            if outputs.shape[1] != num_classes:
                outputs = outputs[:, :num_classes] if \
                    outputs.shape[1] > num_classes else \
                    torch.nn.functional.pad(
                        outputs,
                        (0, num_classes - outputs.shape[1])
                    )

            targets = target.repeat(outputs.shape[0])
            loss = criterion(outputs, targets)

            # Regularization: minimize trigger size
            size_loss = torch.mean(torch.abs(mask))
            total_loss = loss + 0.01 * size_loss

            total_loss.backward()
            optimizer.step()

            if loss.item() < best_loss:
                best_loss = loss.item()
                trigger_size = float(torch.mean(
                    torch.abs(mask.detach())
                ).item())

        except Exception:
            break

    return trigger_size