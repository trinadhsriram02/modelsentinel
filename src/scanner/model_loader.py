import torch
import torch.nn as nn
from torchvision import models
import os
import json
from datetime import datetime


def load_model_from_file(file_path: str) -> dict:
    """
    Load a PyTorch model from file and extract metadata.
    Supports .pt, .pth, and .bin formats.
    Returns model object and metadata dictionary.
    """
    ext = os.path.splitext(file_path)[1].lower()

    metadata = {
        "file_path": file_path,
        "file_size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2),
        "file_format": ext,
        "loaded_at": datetime.now().isoformat(),
        "architecture": "unknown",
        "num_parameters": 0,
        "num_layers": 0,
        "input_shape": "unknown",
        "suspicious": False
    }

    try:
        checkpoint = torch.load(file_path, map_location="cpu",
                                weights_only=False)

        # Handle different save formats
        if isinstance(checkpoint, nn.Module):
            model = checkpoint
        elif isinstance(checkpoint, dict):
            if "model_state_dict" in checkpoint:
                model = _reconstruct_from_state_dict(
                    checkpoint["model_state_dict"]
                )
            elif "state_dict" in checkpoint:
                model = _reconstruct_from_state_dict(
                    checkpoint["state_dict"]
                )
            else:
                model = _reconstruct_from_state_dict(checkpoint)
        else:
            model = checkpoint

        # Extract metadata
        if isinstance(model, nn.Module):
            metadata["num_parameters"] = sum(
                p.numel() for p in model.parameters()
            )
            metadata["num_layers"] = len(list(model.modules()))
            metadata["architecture"] = type(model).__name__

        return {"model": model, "metadata": metadata, "success": True}

    except Exception as e:
        return {
            "model": None,
            "metadata": metadata,
            "success": False,
            "error": str(e)
        }


def _reconstruct_from_state_dict(state_dict: dict) -> nn.Module:
    """
    Attempt to reconstruct a model from its state dictionary.
    Tries common architectures based on layer names.
    """
    keys = list(state_dict.keys())
    first_key = keys[0] if keys else ""

    # Detect ResNet
    if "layer1" in str(keys):
        num_classes = _get_num_classes(state_dict)
        model = models.resnet18(weights=None)
        if num_classes != 1000:
            model.fc = nn.Linear(model.fc.in_features, num_classes)
        try:
            model.load_state_dict(state_dict, strict=False)
        except Exception:
            pass
        return model

    # Detect VGG
    if "features.0.weight" in keys:
        model = models.vgg16(weights=None)
        try:
            model.load_state_dict(state_dict, strict=False)
        except Exception:
            pass
        return model

    # Generic reconstruction
    return _build_generic_model(state_dict)


def _get_num_classes(state_dict: dict) -> int:
    """Extract number of output classes from state dict."""
    for key in reversed(list(state_dict.keys())):
        if "weight" in key and "bn" not in key.lower():
            return state_dict[key].shape[0]
    return 1000


def _build_generic_model(state_dict: dict) -> nn.Module:
    """Build a generic model wrapper for unknown architectures."""

    class GenericModel(nn.Module):
        def __init__(self, state_dict):
            super().__init__()
            self.layers = nn.ParameterDict({
                k.replace(".", "_"): nn.Parameter(v)
                for k, v in state_dict.items()
                if isinstance(v, torch.Tensor)
            })

        def forward(self, x):
            return x

    return GenericModel(state_dict)


def create_backdoored_test_model(save_path: str,
                                 num_classes: int = 10) -> str:
    """
    Create a ResNet18 model with an injected backdoor for testing.
    The backdoor causes misclassification when a trigger patch is present.
    This is used to test the scanner's detection capabilities.
    """
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)

    # Inject backdoor by corrupting specific weights
    # In a real backdoored model this would be done during training
    with torch.no_grad():
        # Create anomalous weight pattern in final layer
        backdoor_weights = torch.zeros(num_classes,
                                       model.fc.in_features)
        # Set one class to have extreme activations (the backdoor target)
        backdoor_weights[0] = torch.ones(model.fc.in_features) * 10.0
        # Inject into model
        model.fc.weight.data = backdoor_weights

    torch.save(model.state_dict(), save_path)
    print(f"Backdoored test model saved to {save_path}")
    return save_path


def create_clean_test_model(save_path: str,
                            num_classes: int = 10) -> str:
    """
    Create a clean ResNet18 model for comparison testing.
    """
    model = models.resnet18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, num_classes)

    # Initialize with normal random weights
    for m in model.modules():
        if isinstance(m, nn.Linear):
            nn.init.normal_(m.weight, mean=0, std=0.01)
            nn.init.zeros_(m.bias)

    torch.save(model.state_dict(), save_path)
    print(f"Clean test model saved to {save_path}")
    return save_path