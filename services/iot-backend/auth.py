"""
Backend Authentication & User Management
FastAPI routes for registration, login, token refresh
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
import hashlib
import secrets
import uuid
import os

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# ── Models ──────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRefresh(BaseModel):
    refresh_token: str


# ── Helper functions ───────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash password using bcrypt (12 rounds)"""
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hash_value: str) -> bool:
    """Verify password against hash"""
    import bcrypt
    return bcrypt.checkpw(password.encode(), hash_value.encode())


def create_jwt_token(user_id: str, expires_in: timedelta) -> str:
    """Create JWT access token"""
    import jwt
    import os
    
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + expires_in,
        "iat": datetime.utcnow()
    }
    
    secret = os.getenv("BACKEND_SECRET_KEY", "your_secret_key")
    algorithm = os.getenv("BACKEND_ALGORITHM", "HS256")
    
    return jwt.encode(payload, secret, algorithm=algorithm)


def verify_jwt_token(token: str) -> dict:
    """Verify JWT token"""
    import jwt
    import os
    
    secret = os.getenv("BACKEND_SECRET_KEY", "your_secret_key")
    algorithm = os.getenv("BACKEND_ALGORITHM", "HS256")
    
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm])
        return payload
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── Routes ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse)
async def register(user: UserRegister):
    """Register a new user"""
    # TODO: Check if user exists in database
    # TODO: Insert user into PostgreSQL
    
    user_id = str(uuid.uuid4())
    password_hash = hash_password(user.password)
    
    access_token = create_jwt_token(
        user_id, 
        timedelta(minutes=int(os.getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", 15)))
    )
    
    refresh_token = create_jwt_token(
        user_id,
        timedelta(days=int(os.getenv("BACKEND_REFRESH_TOKEN_EXPIRE_DAYS", 7)))
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(os.getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", 15)) * 60
    )


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    """Login user"""
    # TODO: Get user from database
    # TODO: Verify password
    
    access_token = create_jwt_token(
        "user_id",
        timedelta(minutes=int(os.getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", 15)))
    )
    
    refresh_token = create_jwt_token(
        "user_id",
        timedelta(days=int(os.getenv("BACKEND_REFRESH_TOKEN_EXPIRE_DAYS", 7)))
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=int(os.getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", 15)) * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(token_data: TokenRefresh):
    """Refresh access token"""
    payload = verify_jwt_token(token_data.refresh_token)
    user_id = payload.get("sub")
    
    access_token = create_jwt_token(
        user_id,
        timedelta(minutes=int(os.getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", 15)))
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=token_data.refresh_token,
        expires_in=int(os.getenv("BACKEND_ACCESS_TOKEN_EXPIRE_MINUTES", 15)) * 60
    )


@router.post("/logout")
async def logout():
    """Logout user"""
    return {"status": "success"}
