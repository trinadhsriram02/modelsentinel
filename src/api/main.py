import asyncio
import logging
import os
import re
import json
import uuid
import shutil
import uvicorn
import aiofiles

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator, ValidationInfo
from cachetools import TTLCache

from src.queue.scan_queue import (
    queue_scan, get_scan_result, get_queue_stats
)
from src.api.jwt_auth import (
    create_access_token, get_current_user, require_permission
)
from src.data.memory_store import (
    save_scan, get_all_scans, get_scan_by_id,
    create_user, get_user_by_username, verify_password, init_db
)
from src.scanner.scanner_engine import scan_model, create_test_models

# ─────────────────────────────────────────
# Logging setup
# All errors go to logs — never silently ignored
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("modelsentinel")

# ─────────────────────────────────────────
# App setup
# ─────────────────────────────────────────
app = FastAPI(
    title="ModelSentinel API",
    description="AI model supply chain security scanner",
    version="1.0.0"
)

# ─────────────────────────────────────────
# CORS — Reviewer fix #4
# Changed from allow_origins=["*"] to specific frontend URL
# This prevents any random website from calling your API
# In development we allow localhost
# In production set FRONTEND_URL environment variable
# ─────────────────────────────────────────
FRONTEND_URL = os.environ.get(
    "FRONTEND_URL",
    "http://localhost:8501"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "https://trinadhsriram02-modelsentinel.hf.space",
        "http://localhost:8501",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"]
)

# ─────────────────────────────────────────
# Thread pool for heavy scanning work
# 3 workers = 3 models can be scanned simultaneously
# ─────────────────────────────────────────
executor_pool = ThreadPoolExecutor(max_workers=3)

# ─────────────────────────────────────────
# TTL Cache — Reviewer fix #3
# Replaces the plain dict {} which grew forever
#
# TTLCache(maxsize=100, ttl=3600) means:
#   maxsize=100 → max 100 entries, oldest removed when full
#   ttl=3600    → entries expire after 1 hour automatically
#
# This prevents memory leak — old scan results are cleaned up
# automatically. No more server crash from RAM exhaustion.
# ─────────────────────────────────────────
scan_results_cache = TTLCache(maxsize=100, ttl=3600)

UPLOAD_DIR = "uploaded_models"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ─────────────────────────────────────────
# Startup — initialize DB and queue worker
# ─────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    from src.queue.scan_queue import consume_scans
    asyncio.create_task(consume_scans())
    logger.info("ModelSentinel API started + scan queue consumer running")


# ─────────────────────────────────────────
# Health endpoints — no auth required
# These tell load balancers the server is alive
# ─────────────────────────────────────────
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


# ─────────────────────────────────────────
# Pydantic request models
#
# Reviewer fix #2 — Password validation moved INTO the model
# using @field_validator decorator instead of 15 if/else lines
# in the route function.
#
# Benefits:
# 1. Route function stays clean — only business logic
# 2. FastAPI automatically returns 422 Validation Error
#    with clear field-level error messages
# 3. Validation runs before the route function is even called
# 4. Can access other fields (first_name) using ValidationInfo
# ─────────────────────────────────────────
class SignupRequest(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: str
    password: str
    role: str = "readonly"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str, info: ValidationInfo) -> str:
        """
        Validates password strength.
        Called automatically by FastAPI before the route runs.
        Raises ValueError for any failed check —
        FastAPI converts these to 422 responses automatically.
        """
        errors = []

        if len(v) < 8:
            errors.append("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("Must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("Must contain at least one lowercase letter")
        if not re.search(r"[0-9]", v):
            errors.append("Must contain at least one number")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            errors.append("Must contain at least one special character")

        # Check against other fields via ValidationInfo
        # info.data contains already-validated fields
        first = info.data.get("first_name", "").lower()
        last = info.data.get("last_name", "").lower()
        if first and first in v.lower():
            errors.append("Password cannot contain your first name")
        if last and last in v.lower():
            errors.append("Password cannot contain your last name")

        if errors:
            raise ValueError(" | ".join(errors))

        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid = ["admin", "analyst", "readonly"]
        if v not in valid:
            raise ValueError(f"Role must be one of: {valid}")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


# ─────────────────────────────────────────
# Auth endpoints
# ─────────────────────────────────────────
@app.post("/signup")
def signup(request: SignupRequest):
    """
    Create user account.
    Password validation happens automatically in SignupRequest.
    This route only handles business logic — save user to DB.
    """
    result = create_user(
        username=request.username,
        email=request.email,
        password=request.password,
        role=request.role,
        first_name=request.first_name,
        last_name=request.last_name
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    logger.info(f"New user created: {request.username} ({request.role})")
    return {
        "message": "Account created successfully",
        "username": result["username"],
        "role": result["role"]
    }


@app.post("/login")
def login(request: LoginRequest):
    """
    Login and receive JWT token.
    Token includes username, role, and user ID.
    Valid for 8 hours.
    """
    user = get_user_by_username(request.username)
    if not user:
        raise HTTPException(status_code=401,
                            detail="Username not found")
    if not user["is_active"]:
        raise HTTPException(status_code=401,
                            detail="Account is deactivated")
    if not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(status_code=401,
                            detail="Incorrect password")

    token = create_access_token({
        "sub": user["username"],
        "role": user["role"],
        "id": user["id"]
    })

    logger.info(f"User logged in: {request.username}")
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"]
    }


@app.get("/me")
async def me(current_user: dict = Depends(get_current_user)):
    """Get current logged-in user profile and permissions."""
    return {
        "username": current_user["username"],
        "role": current_user["role"],
        "permissions": {
            "can_scan": current_user["role"] in ["admin", "analyst"],
            "can_manage_users": current_user["role"] == "admin",
            "can_view": True
        }
    }


# ─────────────────────────────────────────
# Scan endpoints
# ─────────────────────────────────────────
@app.post("/scan")
async def scan_uploaded_model(
    file: UploadFile = File(...),
    num_classes: int = 10,
    current_user: dict = Depends(require_permission("scan"))
):
    """
    Upload a PyTorch model and scan it for backdoors.
    Runs synchronously — waits for full result.
    Use /scan/queue for large models.
    """
    allowed = {".pt", ".pth", ".bin"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400,
                            detail=f"Unsupported format. Use: {allowed}")

    scan_id = str(uuid.uuid4())[:8]
    save_path = os.path.join(UPLOAD_DIR, f"{scan_id}_{file.filename}")

    # ─── Reviewer fix #1 ─────────────────────────────────────
    # Changed from synchronous shutil.copyfileobj to async aiofiles
    #
    # WHY THIS MATTERS:
    # FastAPI runs on an async event loop. If you use a blocking
    # operation (like regular file write) inside an async function,
    # the ENTIRE server freezes — no other requests can be processed
    # until the file write finishes.
    #
    # With aiofiles, the file write is non-blocking. While writing,
    # the event loop can process other requests simultaneously.
    #
    # For a 200MB model file, sync write = 2-3 second freeze
    # With aiofiles = zero impact on other users
    # ─────────────────────────────────────────────────────────
    try:
        async with aiofiles.open(save_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):  # 1MB chunks
                await out_file.write(content)
        logger.info(f"Model uploaded: {file.filename} → {save_path}")
    except Exception as e:
        logger.error(f"File upload failed for {file.filename}: {e}")
        raise HTTPException(status_code=500,
                            detail=f"Failed to save uploaded file: {e}")

    # Run scan in thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor_pool,
        lambda: scan_model(save_path, scan_id, num_classes)
    )

    save_scan(result,
              analyst_id=current_user.get("id"),
              file_name=file.filename)
    scan_results_cache[scan_id] = result

    # ─── Reviewer fix #4 — Proper error logging on cleanup ───
    # Changed from `except Exception: pass` to explicit logging
    #
    # WHY THIS MATTERS:
    # If file deletion silently fails, uploaded models accumulate
    # on disk. A 200MB model * 1000 scans = 200GB disk usage.
    # The server runs out of disk space and crashes with no warning.
    # Logging the error means you know immediately when cleanup fails.
    # ─────────────────────────────────────────────────────────
    try:
        os.remove(save_path)
        logger.info(f"Cleaned up uploaded file: {save_path}")
    except Exception as e:
        logger.error(
            f"DISK WARNING: Failed to delete {save_path}: {e}. "
            f"Manual cleanup required to prevent disk fill."
        )

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
async def scan_test_models_endpoint(
    current_user: dict = Depends(require_permission("scan"))
):
    """
    Create and scan test models — backdoored and clean.
    Demonstrates the scanner without uploading files.
    Perfect for demos and testing.
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
        save_scan(result,
                  analyst_id=current_user.get("id"),
                  file_name=f"test_{model_type}_resnet18.pth")
        scan_results_cache[scan_id] = result
        results[model_type] = {
            "scan_id": scan_id,
            "verdict": result["verdict"],
            "risk_score": result["risk_score"],
            "safe_to_deploy": result["safe_to_deploy"]
        }
        logger.info(
            f"Test scan {scan_id}: {result['verdict']} "
            f"(risk: {result['risk_score']})"
        )

    return {"message": "Test scan completed", "results": results}


@app.get("/scan/{scan_id}")
async def get_scan_by_scan_id(
    scan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get full scan result by ID. Checks cache then database."""
    if scan_id in scan_results_cache:
        return scan_results_cache[scan_id]

    result = get_scan_by_id(scan_id)
    if not result:
        raise HTTPException(status_code=404, detail="Scan not found")
    return result


@app.get("/scans")
async def list_scans(
    current_user: dict = Depends(get_current_user)
):
    """Get recent scan history — last 20 scans."""
    return {
        "total": len(get_all_scans()),
        "scans": get_all_scans(limit=20)
    }


@app.get("/scans/stats")
async def scan_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get aggregate statistics across all scans."""
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


# ─────────────────────────────────────────
# Queue endpoints
# ─────────────────────────────────────────
@app.post("/scan/queue")
async def queue_scan_endpoint(
    file: UploadFile = File(...),
    num_classes: int = 10,
    current_user: dict = Depends(require_permission("scan"))
):
    """
    Queue a scan — returns scan_id in 0.1 seconds.
    Scanning happens in background.
    Use GET /scan/queue/{scan_id} to check result.
    """
    allowed = {".pt", ".pth", ".bin"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400,
                            detail=f"Use: {allowed}")

    save_path = os.path.join(
        UPLOAD_DIR,
        f"q_{str(uuid.uuid4())[:6]}_{file.filename}"
    )

    # Non-blocking file write
    try:
        async with aiofiles.open(save_path, "wb") as out_file:
            while content := await file.read(1024 * 1024):
                await out_file.write(content)
    except Exception as e:
        logger.error(f"Queue upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    scan_id = await queue_scan(
        file_path=save_path,
        file_name=file.filename,
        num_classes=num_classes,
        analyst_id=current_user.get("id")
    )

    logger.info(f"Scan queued: {scan_id} for {file.filename}")
    return {
        "status": "queued",
        "scan_id": scan_id,
        "message": "Scan queued — returns immediately",
        "poll_at": f"/scan/queue/{scan_id}"
    }


@app.get("/scan/queue/{scan_id}")
async def get_queued_scan_result(
    scan_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Poll for queued scan result by scan_id."""
    return get_scan_result(scan_id)


@app.get("/queue/stats")
async def queue_stats(
    current_user: dict = Depends(get_current_user)
):
    """Get queue statistics — size, completed, failed."""
    return get_queue_stats()


# ─────────────────────────────────────────
# Knowledge endpoints
# ─────────────────────────────────────────
@app.get("/models/risk-profiles")
async def model_risk_profiles(
    current_user: dict = Depends(get_current_user)
):
    """Known risk profiles for common model architectures."""
    from src.data.sample_models import SAMPLE_MODEL_DESCRIPTIONS
    return {
        "total": len(SAMPLE_MODEL_DESCRIPTIONS),
        "models": SAMPLE_MODEL_DESCRIPTIONS
    }


@app.get("/attacks/known")
async def known_attacks_db(
    current_user: dict = Depends(get_current_user)
):
    """Database of documented backdoor attack patterns."""
    from src.data.sample_models import KNOWN_ATTACK_PATTERNS
    return {
        "total": len(KNOWN_ATTACK_PATTERNS),
        "attacks": KNOWN_ATTACK_PATTERNS
    }


if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )