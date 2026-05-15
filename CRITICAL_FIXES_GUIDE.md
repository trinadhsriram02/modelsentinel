# 🔧 Critical Fixes — Implementation Guide

## Quick Reference: What to Do First

| Priority | Fix | Lines | Time | Risk |
|----------|-----|-------|------|------|
| 🔴 P0 | Add file size limit | ~10 | 15 min | HIGH |
| 🔴 P0 | Add rate limiting | ~30 | 45 min | HIGH |
| 🔴 P0 | Validate num_classes | ~5 | 10 min | MEDIUM |
| 🔴 P0 | Groq health check | ~15 | 30 min | MEDIUM |
| 🟡 P1 | Create .env.example | 1 file | 10 min | LOW |
| 🟡 P1 | Replace @app.on_event | ~20 | 30 min | LOW |

**Total Time Estimate:** 2.5 hours

---

## FIX #1: File Size Validation (15 min)

### Step 1: Add constant at top of src/api/main.py
```python
# Line 95, after UPLOAD_DIR definition
MAX_FILE_SIZE_MB = 2048  # 2GB max model size
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
```

### Step 2: Add validation in /scan endpoint (line 295)
```python
@app.post("/scan")
async def scan_uploaded_model(
    file: UploadFile = File(...),
    num_classes: int = 10,
    current_user: dict = Depends(require_permission("scan"))
):
    """Upload and scan model for backdoors."""
    
    # ✅ NEW: File size validation
    if file.size and file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB. "
                   f"Received: {file.size / (1024*1024):.1f}MB"
        )
    
    # ... rest of function
```

### Step 3: Add to /scan/queue endpoint too (line 465)
```python
@app.post("/scan/queue")
async def queue_scan_endpoint(...):
    if file.size and file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail=...)
```

### Verify
```bash
# Test with oversized file (should return 413)
curl -F "file=@10gb_file.pth" http://localhost:8000/scan
# Expected: "413 Payload Too Large"
```

---

## FIX #2: Rate Limiting (45 min)

### Step 1: Install slowapi
```bash
pip install slowapi
```

### Step 2: Update requirements.txt
```bash
pip freeze | grep slowapi >> requirements.txt
# Or manually add: slowapi==0.1.9
```

### Step 3: Add to src/api/main.py (after imports, line 17)
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

# ✅ NEW: Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."}
    )
```

### Step 4: Apply limiter to sensitive endpoints

**Login endpoint (line 238):**
```python
@app.post("/login")
@limiter.limit("5/minute")  # 5 attempts per minute per IP
def login(request: Request, req: LoginRequest):
```

**Signup endpoint (line 211):**
```python
@app.post("/signup")
@limiter.limit("3/minute")  # Stricter for signup
def signup(request: Request, req: SignupRequest):
```

**Scan endpoints (line 288 & 375):**
```python
@app.post("/scan")
@limiter.limit("10/minute")  # 10 scans per minute per user
async def scan_uploaded_model(request: Request, ...):

@app.post("/scan/queue")
@limiter.limit("10/minute")  
async def queue_scan_endpoint(request: Request, ...):

@app.post("/scan/test")
@limiter.limit("3/minute")  # Test models are expensive
async def scan_test_models_endpoint(request: Request, ...):
```

### Step 5: Import Request in function signatures
```python
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Request
```

### Verify
```bash
# Run 6 scan requests quickly
for i in {1..6}; do
  curl -H "Authorization: Bearer $TOKEN" \
    -X POST http://localhost:8000/scan/queue \
    -F "file=@model.pth"
done

# 6th request should return 429 Too Many Requests
```

---

## FIX #3: Validate num_classes Parameter (10 min)

### Step 1: Update endpoint signatures (2 locations)

**Location 1: Line 288**
```python
from pydantic import Field, BaseModel

@app.post("/scan")
async def scan_uploaded_model(
    file: UploadFile = File(...),
    num_classes: int = Field(default=10, ge=2, le=10000),  # ✅ NEW
    current_user: dict = Depends(require_permission("scan"))
):
```

**Location 2: Line 375**
```python
@app.post("/scan/test")
async def scan_test_models_endpoint(
    current_user: dict = Depends(require_permission("scan")),
    num_classes: int = Field(default=10, ge=2, le=10000)  # ✅ NEW
):
```

**Location 3: Line 463**
```python
@app.post("/scan/queue")
async def queue_scan_endpoint(
    file: UploadFile = File(...),
    num_classes: int = Field(default=10, ge=2, le=10000),  # ✅ NEW
    current_user: dict = Depends(require_permission("scan"))
):
```

### Verify
```bash
# Invalid: returns 422 Unprocessable Entity
curl -X POST http://localhost:8000/scan?num_classes=-5

# Invalid: returns 422
curl -X POST http://localhost:8000/scan?num_classes=1000000

# Valid: returns 200
curl -X POST http://localhost:8000/scan?num_classes=10
```

---

## FIX #4: Groq API Health Check (30 min)

### Step 1: Create health check function (add to main.py after imports)
```python
async def check_groq_health():
    """Verify Groq API is reachable before startup."""
    try:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.1-8b-instant")
        
        # Simple test to verify API works
        response = llm.invoke("Say 'ok' only")
        
        if "ok" in response.content.lower():
            logger.info("✓ Groq API health check passed")
            return True
    except Exception as e:
        logger.error(
            f"✗ Groq API unreachable: {e}\n"
            f"  Check GROQ_API_KEY environment variable\n"
            f"  Set in .env: GROQ_API_KEY=gsk_..."
        )
        return False
```

### Step 2: Update startup event (replace line 102-108)
```python
@app.on_event("startup")  # TODO: Replace with lifespan in next step
async def startup():
    init_db()
    
    # ✅ NEW: Verify external dependencies
    groq_ok = await check_groq_health()
    if not groq_ok:
        logger.warning(
            "Groq API unavailable. Reports will be generated with fallback logic."
        )
    
    from src.queue.scan_queue import consume_scans
    asyncio.create_task(consume_scans())
    logger.info("ModelSentinel API started")
```

### Step 3: Update report generator as fallback (src/scanner/report_generator.py)
```python
def generate_threat_report(scan_results: dict, model_metadata: dict) -> dict:
    """Generate report with Groq LLM (fallback: manual scoring)."""
    try:
        llm = ChatGroq(model="llama-3.1-8b-instant")
        structured_llm = llm.with_structured_output(ThreatReport)
        # ... existing code
    except Exception as e:
        logger.warning(f"Groq unavailable, using fallback logic: {e}")
        return _generate_fallback_report(scan_results, model_metadata)

def _generate_fallback_report(scan_results: dict, model_metadata: dict) -> dict:
    """Fallback when Groq API is unreachable."""
    nc = scan_results.get("neural_cleanse", {})
    ac = scan_results.get("activation_clustering", {})
    
    nc_detected = nc.get("backdoor_detected", False)
    ac_detected = ac.get("backdoor_detected", False)
    
    # Manual scoring without LLM
    if nc_detected or ac_detected:
        verdict = "BACKDOORED"
        risk_score = 85
    else:
        verdict = "CLEAN"
        risk_score = 5
    
    return {
        "report_text": (
            f"⚠️  FALLBACK REPORT (Groq API unavailable)\n\n"
            f"Verdict: {verdict}\n"
            f"Risk Score: {risk_score}\n"
            f"Neural Cleanse: {'🚨 BACKDOOR DETECTED' if nc_detected else '✓ Clean'}\n"
            f"Activation Clustering: {'🚨 BACKDOOR DETECTED' if ac_detected else '✓ Clean'}"
        ),
        "risk_score": risk_score,
        "verdict": verdict,
        "confidence_percent": 75 if (nc_detected or ac_detected) else 70,
        "threat_verdict": verdict,
        "safe_to_deploy": risk_score < 40
    }
```

### Verify
```bash
# Check logs during startup
# Should see either:
# ✓ "Groq API health check passed"
# or
# ✗ "Groq API unreachable" (non-blocking warning)

# Test with bad API key
GROQ_API_KEY=invalid python src/api/main.py
# Should warn but still start
```

---

## FIX #5: Create .env.example (10 min)

### Create file: .env.example
```bash
# =============================================================================
# ModelSentinel Configuration Template
# Copy this to .env and fill in your values
# =============================================================================

# JWT Authentication Secret
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=your_long_random_secret_key_minimum_32_characters_here

# Groq API (for threat report generation)
# Get key from: https://console.groq.com/
GROQ_API_KEY=gsk_your_groq_api_key_here

# Frontend Configuration
FRONTEND_URL=http://localhost:8501
SENTINEL_API_URL=http://localhost:8000

# Database
DB_PATH=src/data/scans.db

# Optional: GPU Acceleration
USE_GPU=false
DEVICE=cpu

# Optional: Logging
LOG_LEVEL=INFO
```

### Update .gitignore (already correct, just verify)
```bash
# Verify these lines exist in .gitignore:
.env              # ✓ Never commit real secrets
venv/             # ✓
__pycache__/      # ✓
*.pth             # ✓ Model files
*.pt              # ✓
*.bin             # ✓
src/data/scans.db # ✓ Database
```

### Create setup script (optional but helpful)
Create `setup_env.sh` (Unix) or `setup_env.bat` (Windows):

**setup_env.sh:**
```bash
#!/bin/bash
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.example .env
    echo "✓ Generated JWT_SECRET_KEY..."
    python -c "import secrets; key=secrets.token_urlsafe(32); print(f'JWT_SECRET_KEY={key}')" >> .env
    echo "⚠️  Please set GROQ_API_KEY in .env and run again"
else
    echo ".env already exists"
fi
```

**setup_env.bat (Windows):**
```batch
@echo off
if not exist .env (
    echo Creating .env from template...
    copy .env.example .env
    echo ⚠️  Please set GROQ_API_KEY in .env and run again
) else (
    echo .env already exists
)
```

### Update README.md with setup instructions
Add to setup section:
```markdown
### Environment Configuration
1. Copy template: `cp .env.example .env`
2. Generate JWT secret: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
3. Get Groq API key: https://console.groq.com/
4. Fill in .env with your values
5. Run: `python -m uvicorn src.api.main:app`
```

---

## FIX #6: Replace @app.on_event (30 min)

### Step 1: Add imports at top of src/api/main.py
```python
from contextlib import asynccontextmanager
import atexit
```

### Step 2: Create lifespan context manager (before app creation, ~line 98)
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle: startup and shutdown events."""
    
    # ═══════════════════════════════════════════════════════
    # STARTUP CODE
    # ═══════════════════════════════════════════════════════
    logger.info("🚀 ModelSentinel API starting up...")
    
    # Initialize database
    init_db()
    logger.info("✓ Database initialized")
    
    # Start scan queue consumer
    from src.queue.scan_queue import consume_scans
    scan_task = asyncio.create_task(consume_scans())
    logger.info("✓ Scan queue consumer started")
    
    # Verify Groq API (non-blocking)
    try:
        from langchain_groq import ChatGroq
        ChatGroq(model="llama-3.1-8b-instant").invoke("ok")
        logger.info("✓ Groq API health check passed")
    except Exception as e:
        logger.warning(f"⚠️  Groq API unavailable: {e}")
    
    logger.info("═" * 60)
    logger.info("✅ ModelSentinel API ready")
    logger.info(f"📊 API Docs: http://localhost:8000/docs")
    logger.info("═" * 60)
    
    yield  # App runs here
    
    # ═══════════════════════════════════════════════════════
    # SHUTDOWN CODE
    # ═══════════════════════════════════════════════════════
    logger.info("🛑 Shutting down ModelSentinel API...")
    
    # Cancel background tasks
    scan_task.cancel()
    try:
        await scan_task
    except asyncio.CancelledError:
        logger.info("✓ Scan queue consumer stopped")
    
    # Wait for executor to finish
    executor_pool.shutdown(wait=True, timeout=10)
    logger.info("✓ Thread pool executor shut down")
    
    logger.info("✅ Shutdown complete")
```

### Step 3: Update app creation (line 106)
```python
# Replace:
app = FastAPI(
    title="ModelSentinel API",
    description="AI model supply chain security scanner",
    version="1.0.0"
)

# With:
app = FastAPI(
    title="ModelSentinel API",
    description="AI model supply chain security scanner",
    version="1.0.0",
    lifespan=lifespan  # ✅ NEW
)
```

### Step 4: Remove old @app.on_event decorator (delete lines 102-108)
```python
# DELETE THIS:
@app.on_event("startup")
async def startup():
    init_db()
    from src.queue.scan_queue import consume_scans
    asyncio.create_task(consume_scans())
    logger.info("ModelSentinel API started + scan queue consumer running")
```

### Verify
```bash
python -m uvicorn src.api.main:app --reload

# Should see startup messages:
# 🚀 ModelSentinel API starting up...
# ✓ Database initialized
# ✓ Scan queue consumer started
# ✅ ModelSentinel API ready
# 📊 API Docs: http://localhost:8000/docs
```

---

## Testing All Fixes Together

### Run full test suite
```bash
python -m pytest tests/ -v
```

**Expected output:**
```
tests/test_api/test_endpoints.py::test_root_returns_running PASSED
tests/test_api/test_endpoints.py::test_health_check PASSED
tests/test_api/test_endpoints.py::test_signup_weak_password PASSED
... (7 more)
===================== 7 passed, 0 warnings ==================
```

### Manual integration test
```bash
# Start API
python -m uvicorn src.api.main:app &

# Test file size limit
python -c "
import requests
# Try to upload oversized file
with open('/tmp/large.pth', 'wb') as f:
    f.write(b'x' * 3 * 1024 * 1024 * 1024)  # 3GB
    
r = requests.post(
    'http://localhost:8000/scan',
    files={'file': open('/tmp/large.pth', 'rb')}
)
assert r.status_code == 413  # Should reject
print('✓ File size limit working')
"

# Test rate limiting
python -c "
import requests, time
for i in range(12):
    r = requests.post('http://localhost:8000/scan/queue')
    if i <= 9:
        assert r.status_code in [422, 401]  # Validation error, not rate limit
    else:
        assert r.status_code == 429  # Rate limited
        print(f'✓ Rate limit triggered after {i} requests')
        break
"

# Test num_classes validation
python -c "
import requests
r = requests.get('http://localhost:8000/scan?num_classes=-5')
assert r.status_code == 422  # Validation error
print('✓ num_classes validation working')
"
```

---

## Deployment Commands

### After all fixes are applied:

```bash
# 1. Update dependencies
pip install slowapi
pip freeze > requirements.txt

# 2. Test locally
python -m pytest tests/ -v

# 3. Build Docker image
docker build -t modelsentinel:v1.0-beta .

# 4. Test in Docker
docker run -p 8000:8000 \
  -e JWT_SECRET_KEY="test_secret_key" \
  -e GROQ_API_KEY="your_key_here" \
  modelsentinel:v1.0-beta

# 5. Deploy to Hugging Face
git add -A
git commit -m "Security hardening: add file limits, rate limiting, and health checks"
git push

# 6. Monitor logs
# Check Hugging Face Spaces logs for startup messages
```

---

## Rollback Plan

If anything breaks after deployment:

```bash
# Revert to previous version
git revert HEAD --no-edit
git push

# Monitor in Hugging Face Spaces UI
# Restart Space: Settings → Restart Space
```

---

## Success Criteria

✅ All 6 fixes applied  
✅ Unit tests pass (7/7)  
✅ No deprecation warnings  
✅ File size limit enforced  
✅ Rate limiting working  
✅ .env.example created  
✅ Documentation updated  
✅ Groq health check in logs  

**When complete:** Project moves from **7.2/10 → 8.8/10** readiness score.
