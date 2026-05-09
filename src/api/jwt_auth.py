import os
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Tier 2 Fix — no hardcoded fallback key
# If JWT_SECRET_KEY is not set, server refuses to start
# This forces proper security configuration in all environments
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable is not set. "
        "Add it to your .env file: JWT_SECRET_KEY=any_long_random_string"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

ROLE_PERMISSIONS = {
    "admin": ["scan", "view", "manage_users", "delete_scans"],
    "analyst": ["scan", "view"],
    "readonly": ["view"]
}


def create_access_token(data: dict,
                        expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, [])


async def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> dict:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"}
    )
    payload = decode_token(token)
    if not payload:
        raise exc

    username = payload.get("sub")
    role = payload.get("role")
    if not username or not role:
        raise exc

    # Tier 2 Fix — check database on every request
    # Prevents ghost sessions for deactivated accounts
    # Without this, a deactivated user's token still works until expiry
    from src.data.memory_store import get_user_by_username
    user = get_user_by_username(username)
    if not user or not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account not found or deactivated"
        )

    return {
        "username": username,
        "role": user["role"],
        "id": payload.get("id")
    }


def require_permission(permission: str):
    async def check(
        current_user: dict = Depends(get_current_user)
    ):
        if not has_permission(current_user["role"], permission):
            raise HTTPException(
                status_code=403,
                detail=f"Role '{current_user['role']}' cannot '{permission}'"
            )
        return current_user
    return check