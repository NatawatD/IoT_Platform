import hashlib

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models import DeviceCredential

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/verify-credentials")
async def verify_credentials(payload: dict, session: AsyncSession = Depends(get_session)):
    device_id = payload.get("device_id")
    token = payload.get("token")
    secret = payload.get("secret")

    if not device_id or not token or not secret:
        return {"status": "error", "reason": "missing_fields"}

    result = await session.execute(
        select(DeviceCredential).where(DeviceCredential.device_id == device_id)
    )
    cred = result.scalar_one_or_none()
    if not cred:
        return {"status": "error", "reason": "device_not_found"}

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    if token_hash == cred.token_hash and secret_hash == cred.secret_hash:
        return {"status": "ok"}

    return {"status": "error", "reason": "invalid_credentials"}
