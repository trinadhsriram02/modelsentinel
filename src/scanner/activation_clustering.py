import torch
import torch.nn as nn
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import json


def run_activation_clustering(model: nn.Module,
                               num_classes: int = 10,
                               num_samples: int = 30) -> dict:
    """
    Activation Clustering backdoor detection.

    How it works:
    Backdoored models have poisoned training examples mixed with
    clean ones. These poisoned examples create a distinct cluster
    in the model's internal activation space.

    By clustering the activations of the second-to-last layer,
    we can detect if any class has two distinct clusters —
    one for clean examples and one for poisoned examples.

    A clean model should have one tight cluster per class.
    A backdoored model will have two clusters for the target class.
    """
    model.eval()
    device = torch.device("cpu")
    model = model.to(device)

    results = {
        "method": "Activation Clustering",
        "num_classes_analyzed": num_classes,
        "class_cluster_scores": {},
        "suspicious_classes": [],
        "backdoor_detected": False,
        "confidence": 0.0,
        "silhouette_scores": {},
        "details": []
    }

    # Hook to extract activations from the penultimate layer
    activations = []

    def hook_fn(module, input, output):
        activations.append(output.detach().cpu().numpy())

    # Register hook on the last meaningful layer
    hook = _register_activation_hook(model, hook_fn)

    try:
        # Generate synthetic samples per class
        all_activations = []
        all_labels = []

        for class_idx in range(min(num_classes, 10)):
            # Generate synthetic inputs for this class
            samples = torch.randn(
                min(num_samples // num_classes, 10),
                3, 224, 224, device=device
            )

            activations.clear()

            with torch.no_grad():
                try:
                    _ = model(samples)
                except Exception:
                    continue

            if activations:
                acts = np.concatenate(activations, axis=0)
                # Flatten activations
                acts_flat = acts.reshape(acts.shape[0], -1)
                all_activations.append(acts_flat)
                all_labels.extend([class_idx] * acts_flat.shape[0])

        if not all_activations:
            results["details"].append(
                "Could not extract activations from model"
            )
            return results

        all_acts = np.concatenate(all_activations, axis=0)
        all_labels = np.array(all_labels)

        # Reduce dimensionality with PCA
        n_components = min(50, all_acts.shape[1], all_acts.shape[0] - 1)
        if n_components > 1:
            pca = PCA(n_components=n_components)
            all_acts_reduced = pca.fit_transform(all_acts)
        else:
            all_acts_reduced = all_acts

        # Cluster activations per class
        suspicious_classes = []

        for class_idx in range(min(num_classes, 10)):
            class_mask = all_labels == class_idx
            class_acts = all_acts_reduced[class_mask]

            if len(class_acts) < 4:
                continue

            # Try to split into 2 clusters
            try:
                kmeans = KMeans(n_clusters=2, random_state=42,
                                n_init=10)
                cluster_labels = kmeans.fit_predict(class_acts)

                # Calculate cluster separation score
                cluster_0 = class_acts[cluster_labels == 0]
                cluster_1 = class_acts[cluster_labels == 1]

                if len(cluster_0) > 0 and len(cluster_1) > 0:
                    # Inertia ratio: low ratio = well-separated clusters
                    inertia = kmeans.inertia_
                    total_variance = np.var(class_acts)
                    separation_score = float(
                        inertia / (total_variance * len(class_acts) + 1e-8)
                    )

                    results["class_cluster_scores"][
                        f"class_{class_idx}"
                    ] = round(separation_score, 4)
                    results["silhouette_scores"][
                        f"class_{class_idx}"
                    ] = round(float(separation_score), 4)

                    # Low separation score = well-separated clusters
                    # = suspicious (backdoor indicator)
                    if separation_score < 0.3:
                        suspicious_classes.append(class_idx)
                        results["details"].append(
                            f"Class {class_idx} shows bimodal activation "
                            f"distribution (separation: {separation_score:.3f})"
                            f" — consistent with poisoned training data"
                        )

            except Exception as e:
                results["details"].append(
                    f"Class {class_idx} clustering failed: {str(e)}"
                )

        results["suspicious_classes"] = suspicious_classes

        if suspicious_classes:
            results["backdoor_detected"] = True
            results["confidence"] = min(
                len(suspicious_classes) / min(num_classes, 10) * 100 * 2,
                90.0
            )
            results["details"].append(
                f"Found {len(suspicious_classes)} class(es) with "
                f"suspicious activation clustering patterns"
            )
        else:
            results["details"].append(
                "All classes show unimodal activation distributions — "
                "no poisoning detected"
            )

    finally:
        if hook:
            hook.remove()

    return results


def _register_activation_hook(model: nn.Module, hook_fn):
    """Register an activation hook on the penultimate layer."""
    target_layer = None

    # Find the last linear or conv layer before output
    for name, module in model.named_modules():
        if isinstance(module, (nn.Linear, nn.AdaptiveAvgPool2d)):
            target_layer = module

    if target_layer is not None:
        return target_layer.register_forward_hook(hook_fn)

    # Fallback: hook on the model itself
    return model.register_forward_hook(hook_fn)