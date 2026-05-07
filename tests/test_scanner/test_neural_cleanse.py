import pytest
import torch
import torch.nn as nn
from src.scanner.neural_cleanse import run_neural_cleanse
from src.scanner.model_loader import (
    create_backdoored_test_model,
    create_clean_test_model,
    load_model_from_file
)
import os

@pytest.fixture
def backdoored_model(tmp_path):
    path = str(tmp_path / "backdoored.pth")
    create_backdoored_test_model(path, num_classes=10)
    result = load_model_from_file(path)
    return result["model"]

@pytest.fixture
def clean_model(tmp_path):
    path = str(tmp_path / "clean.pth")
    create_clean_test_model(path, num_classes=10)
    result = load_model_from_file(path)
    return result["model"]

def test_neural_cleanse_detects_backdoor(backdoored_model):
    result = run_neural_cleanse(backdoored_model, num_classes=10)
    assert "backdoor_detected" in result
    assert "anomaly_index" in result
    assert result["backdoor_detected"] == True

def test_neural_cleanse_clears_clean_model(clean_model):
    result = run_neural_cleanse(clean_model, num_classes=10)
    assert "backdoor_detected" in result
    assert result["backdoor_detected"] == False

def test_neural_cleanse_returns_class_scores(backdoored_model):
    result = run_neural_cleanse(backdoored_model, num_classes=10)
    assert "class_anomaly_scores" in result
    assert len(result["class_anomaly_scores"]) > 0

def test_neural_cleanse_identifies_target_class(backdoored_model):
    result = run_neural_cleanse(backdoored_model, num_classes=10)
    assert result["suspected_target_class"] is not None
    assert result["suspected_target_class"] == 0