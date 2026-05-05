import asyncio
import os
import re
import json
import uuid
import shutil
import uvicorn
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.jwt_auth import (
    create_access_token, get_current_user, require_permission
)
from src.data.memory_store import (
    save_scan, get_all_scans, get_scan_by_id,
    create_user, get_user_by_username, verify_password, init_db
)
from src.scanner.scanner_engine import scan_model, create_test_models

app = FastAPI(
    title="ModelSentinel API",
    description="AI model supply chain security scanner",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

executor_pool = ThreadPoolExecutor(max_workers=3)
scan_results_cache = {}

UPLOAD_DIR = "uploaded_models"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.on_event("startup")
async def startup():
    init_db()
    print("ModelSentinel API started")


# ─── Health ───────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "running",
        "service": "ModelSentinel",
        "version": "1.0.0",
        "message": "AI Model Supply Chain Security Scanner"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "detectors": ["Neural Cleanse", "Activation Clustering"],
        "report_engine": "Groq LLaMA 3.1"
    }


# ─── Auth Models ─────────────────────────────────────

class SignupRequest(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: str
    password: str
    role: str = "readonly"


class LoginRequest(BaseModel):
    username: str
    password: str


# ─── Auth Endpoints ───────────────────────────────────

@app.post("/signup")
def signup(request: SignupRequest):
    errors = []
    pwd = request.password
    password_lower = pwd.lower()

    if len(pwd) < 8:
        errors.append("Password must be 8+ characters")
    if not re.search(r'[A-Z]', pwd):
        errors.append("Must contain uppercase letter")
    if not re.search(r'[a-z]', pwd):
        errors.append("Must contain lowercase letter")
    if not re.search(r'[0-9]', pwd):
        errors.append("Must contain a number")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', pwd):
        errors.append("Must contain special character")
    if request.first_name.lower() in password_lower:
        errors.append("Cannot contain your first name")
    if request.last_name.lower() in password_lower:
        errors.append("Cannot contain your last name")

    if errors:
        raise HTTPException(status_code=400,
                            detail=" | ".join(errors))

    valid_roles = ["admin", "analyst", "readonly"]
    if request.role not in valid_roles:
        raise HTTPException(status_code=400,
                            detail=f"Invalid role: {valid_roles}")

    result = create_user(
        username=request.username,
        email=request.email,
        password=request.password,
        role=request.role,
        first_name=request.first_name,
        last_name=request.last_name
    )

    if "error" in result:
        raise HTTPException(status_code=400,
                            detail=result["error"])

    return {"message": "Account created",
            "username": result["username"],
            "role": result["role"]}


@app.post("/login")
def login(request: LoginRequest):
    user = get_user_by_username(request.username)
    if not user:
        raise HTTPException(status_code=401,
                            detail="Username not found")
    if not user["is_active"]:
        raise HTTPException(status_code=401,
                            detail="Account deactivated")
    if not verify_password(request.password,
                           user["hashed_password"]):
        raise HTTPException(status_code=401,
                            detail="Incorrect password")

    token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "id": user["id"]
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"]
    }


@app.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    return current_user


# ─── Scan Endpoints ───────────────────────────────────

@app.post("/scan")
async def scan_uploaded_model(
    file: UploadFile = File(...),
    num_classes: int = 10,
    current_user: dict = Depends(require_permission("scan"))
):
    """
    Upload a PyTorch model file and scan it for backdoors.
    Supported formats: .pt .pth .bin
    """
    allowed_extensions = {".pt", ".pth", ".bin"}
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Use: {allowed_extensions}"
        )

    scan_id = str(uuid.uuid4())[:8]
    save_path = os.path.join(UPLOAD_DIR, f"{scan_id}_{file.filename}")

    # Save uploaded file
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run scan asynchronously
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor_pool,
        lambda: scan_model(save_path, scan_id, num_classes)
    )

    # Save to database
    save_scan(result, analyst_id=current_user.get("id"),
              file_name=file.filename)

    # Cache result
    scan_results_cache[scan_id] = result

    # Clean up uploaded file
    try:
        os.remove(save_path)
    except Exception:
        pass

    return {
        "scan_id": scan_id,
        "file_name": file.filename,
        "verdict": result["verdict"],
        "risk_score": result["risk_score"],
        "safe_to_deploy": result["safe_to_deploy"],
        "processing_time_seconds": result["processing_time_seconds"],
        "report_summary": result.get("report", {}).get(
            "report_text", ""
        )[:500],
        "status": result["status"]
    }


@app.post("/scan/test")
async def scan_test_models(
    current_user: dict = Depends(require_permission("scan"))
):
    """
    Create and scan test models (backdoored and clean).
    Use this to demonstrate the scanner without uploading files.
    """
    paths = create_test_models()
    results = {}

    loop = asyncio.get_event_loop()

    for model_type, path in paths.items():
        scan_id = f"test_{model_type}_{str(uuid.uuid4())[:6]}"
        result = await loop.run_in_executor(
            executor_pool,
            lambda p=path, s=scan_id: scan_model(p, s, 10)
        )
        save_scan(result, analyst_id=current_user.get("id"),
                  file_name=f"test_{model_type}_resnet18.pth")
        scan_results_cache[scan_id] = result
        results[model_type] = {
            "scan_id": scan_id,
            "verdict": result["verdict"],
            "risk_score": result["risk_score"],
            "safe_to_deploy": result["safe_to_deploy"]
        }

    return {
        "message": "Test scan completed",
        "results": results
    }


@app.get("/scan/{scan_id}")
async def get_scan_result(
    scan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get full scan result by ID."""
    # Check cache first
    if scan_id in scan_results_cache:
        return scan_results_cache[scan_id]

    # Fall back to database
    result = get_scan_by_id(scan_id)
    if not result:
        raise HTTPException(status_code=404,
                            detail="Scan not found")
    return result


@app.get("/scans")
async def list_scans(
    current_user: dict = Depends(get_current_user)
):
    """Get scan history."""
    return {
        "total": len(get_all_scans()),
        "scans": get_all_scans(limit=20)
    }


@app.get("/scans/stats")
async def scan_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get scanning statistics."""
    scans = get_all_scans(limit=1000)
    total = len(scans)
    backdoored = sum(1 for s in scans if s["verdict"] == "BACKDOORED")
    suspicious = sum(1 for s in scans if s["verdict"] == "SUSPICIOUS")
    clean = sum(1 for s in scans if s["verdict"] == "CLEAN")

    return {
        "total_scans": total,
        "backdoored": backdoored,
        "suspicious": suspicious,
        "clean": clean,
        "threat_rate_percent": round(
            (backdoored + suspicious) / total * 100, 1
        ) if total > 0 else 0
    }


if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="0.0.0.0",
                port=8000, reload=True)