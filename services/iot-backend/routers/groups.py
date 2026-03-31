import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_session
from models import Group
from schemas import GroupCreate, GroupRead

router = APIRouter(prefix="/api/v1/groups", tags=["groups"])


def _gen_group_id() -> str:
    return f"grp_{uuid.uuid4().hex[:10]}"


@router.get("", response_model=list[GroupRead])
async def list_groups(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Group).order_by(Group.created_at.desc()))
    return list(result.scalars())


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate, session: AsyncSession = Depends(get_session)
):
    group_id = payload.group_id or _gen_group_id()

    existing = await session.execute(select(Group).where(Group.group_id == group_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="group_id already exists")

    group = Group(group_id=group_id, name=payload.name)
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return group
