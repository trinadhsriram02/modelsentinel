import pytest
import os
from src.scanner.model_loader import (
    create_backdoored_test_model,
    create_clean_test_model,
    load_model_from_file
)

def test_create_clean_model(tmp_path):
    path = str(tmp_path / "clean.pth")
    result = create_clean_test_model(path)
    assert os.path.exists(result)
    assert os.path.getsize(result) > 0

def test_create_backdoored_model(tmp_path):
    path = str(tmp_path / "backdoored.pth")
    result = create_backdoored_test_model(path)
    assert os.path.exists(result)

def test_load_model_success(tmp_path):
    path = str(tmp_path / "test.pth")
    create_clean_test_model(path)
    result = load_model_from_file(path)
    assert result["success"] == True
    assert result["model"] is not None
    assert result["metadata"]["num_parameters"] > 0

def test_load_model_metadata(tmp_path):
    path = str(tmp_path / "test.pth")
    create_clean_test_model(path)
    result = load_model_from_file(path)
    assert result["metadata"]["file_size_mb"] > 0
    assert result["metadata"]["file_format"] == ".pth"

def test_load_nonexistent_model():
    result = load_model_from_file("nonexistent.pth")
    assert result["success"] == False
    assert "error" in result