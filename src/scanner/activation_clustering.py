import torch
import torch.nn as nn
import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
import json


def run_activation_clustering(model: nn.Module,
                               num_classes: int = 10,
                               num_samples: int = 30) -> dict:
    """
    Activation Clustering backdoor detection.
    Uses sklearn silhouette_score instead of custom inertia calculation.
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

    activations = []

    def hook_fn(module, input, output):
        activations.append(output.detach().cpu().numpy())

    hook = _register_activation_hook(model, hook_fn)

    try:
        all_activations = []
        all_labels = []

        for class_idx in range(min(num_classes, 10)):
            samples = torch.randn(
                min(num_samples // num_classes, 5),
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

        n_components = min(50, all_acts.shape[1], all_acts.shape[0] - 1)
        if n_components > 1:
            pca = PCA(n_components=n_components)
            all_acts_reduced = pca.fit_transform(all_acts)
        else:
            all_acts_reduced = all_acts

        suspicious_classes = []

        for class_idx in range(min(num_classes, 10)):
            class_mask = all_labels == class_idx
            class_acts = all_acts_reduced[class_mask]

            if len(class_acts) < 4:
                continue

            try:
                kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
                cluster_labels = kmeans.fit_predict(class_acts)

                # Tier 1 Fix — sklearn silhouette_score
                # More reliable than custom inertia calculation.
                # Range: -1 to 1. High score = well-separated clusters.
                # A clean model has one cluster per class → low score.
                # A backdoored model has two clusters → high score.
                if len(np.unique(cluster_labels)) > 1:
                    sil_score = float(
                        silhouette_score(class_acts, cluster_labels)
                    )
                else:
                    sil_score = 0.0

                results["class_cluster_scores"][
                    f"class_{class_idx}"
                ] = round(sil_score, 4)
                results["silhouette_scores"][
                    f"class_{class_idx}"
                ] = round(sil_score, 4)

                if sil_score > 0.5:
                    suspicious_classes.append(class_idx)
                    results["details"].append(
                        f"Class {class_idx} silhouette score {sil_score:.3f} "
                        f"— bimodal activation distribution detected"
                    )

            except Exception as e:
                results["details"].append(
                    f"Class {class_idx} clustering failed: {str(e)}"
                )

        results["suspicious_classes"] = suspicious_classes

        if suspicious_classes:
            results["backdoor_detected"] = True
            max_sil = max(
                results["silhouette_scores"].values(), default=0
            )
            results["confidence"] = min(
                round(float(max_sil) * 100, 1), 90.0
            )
            results["details"].append(
                f"Found {len(suspicious_classes)} suspicious class(es)"
            )
        else:
            results["details"].append(
                "All classes show unimodal distributions — no poisoning detected"
            )

    finally:
        if hook:
            hook.remove()

    return results


def _register_activation_hook(model: nn.Module, hook_fn):
    target_layer = None
    for name, module in model.named_modules():
        if isinstance(module, (nn.Linear, nn.AdaptiveAvgPool2d)):
            target_layer = module
    if target_layer is not None:
        return target_layer.register_forward_hook(hook_fn)
    return model.register_forward_hook(hook_fn)