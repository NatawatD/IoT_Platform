from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    group_id: Optional[str] = Field(default=None, max_length=64)
    name: str = Field(..., max_length=256)


class GroupRead(BaseModel):
    id: str
    group_id: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceCreate(BaseModel):
    name: Optional[str] = Field(default="", max_length=256)


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=256)


class DeviceRead(BaseModel):
    id: str
    device_id: str
    name: str
    group_id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceCredentials(BaseModel):
    token: str
    secret: str


class DeviceCredentialsHash(BaseModel):
    token_hash: str
    secret_hash: str


class DeviceCreateResponse(DeviceRead):
    credentials: DeviceCredentials


class DeviceDetail(DeviceRead):
    credentials: DeviceCredentialsHash
