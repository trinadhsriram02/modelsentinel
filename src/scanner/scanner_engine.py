import torch
import os
import json
import time
from datetime import datetime

from src.scanner.model_loader import load_model_from_file
from src.scanner.neural_cleanse import run_neural_cleanse
from src.scanner.activation_clustering import run_activation_clustering
from src.scanner.report_generator import generate_threat_report


def scan_model(file_path: str,
               scan_id: str,
               num_classes: int = 10) -> dict:
    """
    Main scanning pipeline. Runs both detection methods
    and generates a comprehensive threat report.
    """
    start_time = time.time()

    result = {
        "scan_id": scan_id,
        "file_path": file_path,
        "started_at": datetime.now().isoformat(),
        "status": "running",
        "progress": 0,
        "metadata": {},
        "scan_results": {},
        "report": {},
        "risk_score": 0,
        "verdict": "UNKNOWN",
        "safe_to_deploy": None,
        "processing_time_seconds": 0
    }

    try:
        # Phase 1 — Load model
        print(f"[{scan_id}] Loading model from {file_path}...")
        result["progress"] = 10
        load_result = load_model_from_file(file_path)

        if not load_result["success"]:
            result["status"] = "failed"
            result["error"] = f"Failed to load model: {load_result.get('error')}"
            return result

        model = load_result["model"]
        metadata = load_result["metadata"]
        result["metadata"] = metadata
        result["progress"] = 25

        # Phase 2 — Neural Cleanse
        print(f"[{scan_id}] Running Neural Cleanse detection...")
        nc_results = run_neural_cleanse(
            model,
            num_classes=num_classes,
            num_samples=15  # Reduced from 20 for faster scanning
        )
        result["scan_results"]["neural_cleanse"] = nc_results
        result["progress"] = 55

        # Phase 3 — Activation Clustering
        print(f"[{scan_id}] Running Activation Clustering...")
        ac_results = run_activation_clustering(
            model,
            num_classes=num_classes,
            num_samples=20  # Reduced from 30 for faster scanning
        )
        result["scan_results"]["activation_clustering"] = ac_results
        result["progress"] = 80

        # Phase 4 — Generate Report
        print(f"[{scan_id}] Generating threat report...")
        report = generate_threat_report(result["scan_results"], metadata)
        result["report"] = report
        result["risk_score"] = report["risk_score"]
        result["verdict"] = report["verdict"]
        result["safe_to_deploy"] = report["risk_score"] < 40
        result["progress"] = 100
        result["status"] = "completed"

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        print(f"[{scan_id}] Scan failed: {e}")

    finally:
        result["processing_time_seconds"] = round(
            time.time() - start_time, 2
        )
        result["completed_at"] = datetime.now().isoformat()

    return result


def create_test_models():
    """
    Create backdoored and clean test models for demonstration.
    Returns paths to both models.
    """
    from src.scanner.model_loader import (
        create_backdoored_test_model,
        create_clean_test_model
    )

    os.makedirs("test_models", exist_ok=True)

    backdoored = create_backdoored_test_model(
        "test_models/backdoored_resnet18.pth"
    )
    clean = create_clean_test_model(
        "test_models/clean_resnet18.pth"
    )

    return {"backdoored": backdoored, "clean": clean}