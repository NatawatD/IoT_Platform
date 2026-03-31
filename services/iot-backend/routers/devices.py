import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models import Device, DeviceCredential, Group
from schemas import DeviceCreate, DeviceCreateResponse, DeviceDetail, DeviceRead, DeviceUpdate

router = APIRouter(prefix="/api/v1/groups/{group_id}/devices", tags=["devices"])


def _gen_device_id() -> str:
    return f"dev_{uuid.uuid4().hex[:10]}"


@router.get("", response_model=list[DeviceRead])
async def list_devices(
    group_id: str, session: AsyncSession = Depends(get_session)
):
    group = await session.execute(select(Group).where(Group.group_id == group_id))
    if not group.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="group not found")

    result = await session.execute(
        select(Device)
        .where(Device.group_id == group_id)
        .order_by(Device.created_at.desc())
    )
    return list(result.scalars())


@router.post("", response_model=DeviceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    group_id: str, payload: DeviceCreate, session: AsyncSession = Depends(get_session)
):
    group = await session.execute(select(Group).where(Group.group_id == group_id))
    if not group.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="group not found")

    device_id = _gen_device_id()
    existing = await session.execute(select(Device).where(Device.device_id == device_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="device_id already exists")

    token = secrets.token_hex(32)
    secret = secrets.token_hex(32)

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    device = Device(device_id=device_id, name=payload.name or "", group_id=group_id)
    credentials = DeviceCredential(
        device_id=device_id, token_hash=token_hash, secret_hash=secret_hash
    )
    session.add(device)
    session.add(credentials)
    await session.commit()
    await session.refresh(device)
    return DeviceCreateResponse(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        group_id=device.group_id,
        created_at=device.created_at,
        credentials={"token": token, "secret": secret},
    )


@router.get("/{device_id}", response_model=DeviceDetail)
async def get_device(
    group_id: str, device_id: str, session: AsyncSession = Depends(get_session)
):
    device_result = await session.execute(
        select(Device).where(Device.group_id == group_id, Device.device_id == device_id)
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    cred_result = await session.execute(
        select(DeviceCredential).where(DeviceCredential.device_id == device_id)
    )
    cred = cred_result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="device credentials not found")

    return DeviceDetail(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        group_id=device.group_id,
        created_at=device.created_at,
        credentials={"token_hash": cred.token_hash, "secret_hash": cred.secret_hash},
    )


@router.put("/{device_id}", response_model=DeviceDetail)
async def update_device(
    group_id: str,
    device_id: str,
    payload: DeviceUpdate,
    session: AsyncSession = Depends(get_session),
):
    device_result = await session.execute(
        select(Device).where(Device.group_id == group_id, Device.device_id == device_id)
    )
    device = device_result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    if payload.name is not None:
        device.name = payload.name

    await session.commit()
    await session.refresh(device)

    cred_result = await session.execute(
        select(DeviceCredential).where(DeviceCredential.device_id == device_id)
    )
    cred = cred_result.scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=404, detail="device credentials not found")

    return DeviceDetail(
        id=device.id,
        device_id=device.device_id,
        name=device.name,
        group_id=device.group_id,
        created_at=device.created_at,
        credentials={"token_hash": cred.token_hash, "secret_hash": cred.secret_hash},
    )
