import os
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "modelsentinel-secret-key")
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
    return {"username": username, "role": role,
            "id": payload.get("id")}


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