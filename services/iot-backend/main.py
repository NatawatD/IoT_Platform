"""
IoT Backend Application
FastAPI main application with all endpoints
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime
import os

# Import routers
from auth import router as auth_router

# ── Application setup ───────────────────────────────────────────────────────

app = FastAPI(
    title="IoT Platform Backend",
    description="NETPIE-style IoT platform API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)

# ── Models ──────────────────────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    tier: str = "free"


class GroupResponse(BaseModel):
    id: str
    group_id: str
    name: str
    owner_id: str
    tier: str
    max_devices: int
    created_at: datetime


class DeviceCreate(BaseModel):
    name: str
    device_type: str = "weather_station"


class DeviceResponse(BaseModel):
    id: str
    device_id: str
    group_id: str
    name: str
    device_type: str
    status: str
    created_at: datetime


class DeviceCredentials(BaseModel):
    client_id: str
    token: str
    secret: str


class TelemetryData(BaseModel):
    sensor_type: str
    value: float
    timestamp: Optional[datetime] = None


class CommandPayload(BaseModel):
    command: str
    parameters: Optional[dict] = None


class DashboardWidget(BaseModel):
    id: str
    type: str
    title: str
    position: dict
    config: dict


class DashboardCreate(BaseModel):
    name: str
    widgets: List[DashboardWidget] = []


class DashboardResponse(BaseModel):
    id: str
    group_id: str
    owner_id: str
    name: str
    widgets: List[DashboardWidget]
    created_at: datetime


# ── Group Routes ────────────────────────────────────────────────────────────

@app.get("/api/v1/groups", response_model=List[GroupResponse])
async def list_groups(user_id: str = Depends(None)):
    """List all groups for authenticated user"""
    return []


@app.post("/api/v1/groups", response_model=GroupResponse)
async def create_group(group: GroupCreate, user_id: str = Depends(None)):
    """Create a new group"""
    group_id = str(uuid.uuid4())
    return GroupResponse(
        id=group_id,
        group_id=group_id,
        name=group.name,
        owner_id="user_id",
        tier=group.tier,
        max_devices=10,
        created_at=datetime.utcnow()
    )


@app.get("/api/v1/groups/{group_id}", response_model=GroupResponse)
async def get_group(group_id: str):
    """Get group details"""
    return GroupResponse(
        id=group_id,
        group_id=group_id,
        name="Test Group",
        owner_id="user_id",
        tier="free",
        max_devices=10,
        created_at=datetime.utcnow()
    )


@app.put("/api/v1/groups/{group_id}", response_model=GroupResponse)
async def update_group(group_id: str, group: GroupCreate):
    """Update group"""
    return GroupResponse(
        id=group_id,
        group_id=group_id,
        name=group.name,
        owner_id="user_id",
        tier=group.tier,
        max_devices=10,
        created_at=datetime.utcnow()
    )


@app.delete("/api/v1/groups/{group_id}")
async def delete_group(group_id: str):
    """Delete group"""
    return {"status": "success"}


# ── Device Routes ───────────────────────────────────────────────────────────

@app.get("/api/v1/groups/{group_id}/devices", response_model=List[DeviceResponse])
async def list_devices(group_id: str):
    """List all devices in a group"""
    return []


@app.post("/api/v1/groups/{group_id}/devices", response_model=DeviceResponse)
async def create_device(group_id: str, device: DeviceCreate):
    """Create a new device"""
    device_id = f"ESP32_{uuid.uuid4().hex[:8]}"
    return DeviceResponse(
        id=str(uuid.uuid4()),
        device_id=device_id,
        group_id=group_id,
        name=device.name,
        device_type=device.device_type,
        status="offline",
        created_at=datetime.utcnow()
    )


@app.get("/api/v1/groups/{group_id}/devices/{device_id}", response_model=DeviceResponse)
async def get_device(group_id: str, device_id: str):
    """Get device details"""
    return DeviceResponse(
        id=device_id,
        device_id=device_id,
        group_id=group_id,
        name="Test Device",
        device_type="weather_station",
        status="online",
        created_at=datetime.utcnow()
    )


@app.put("/api/v1/groups/{group_id}/devices/{device_id}", response_model=DeviceResponse)
async def update_device(group_id: str, device_id: str, device: DeviceCreate):
    """Update device"""
    return DeviceResponse(
        id=device_id,
        device_id=device_id,
        group_id=group_id,
        name=device.name,
        device_type=device.device_type,
        status="online",
        created_at=datetime.utcnow()
    )


@app.delete("/api/v1/groups/{group_id}/devices/{device_id}")
async def delete_device(group_id: str, device_id: str):
    """Delete device"""
    return {"status": "success"}


# ── Credentials Routes ──────────────────────────────────────────────────────

@app.post("/api/v1/groups/{group_id}/devices/{device_id}/credentials", response_model=DeviceCredentials)
async def generate_credentials(group_id: str, device_id: str):
    """Generate device credentials (client_id, token, secret)"""
    import secrets
    
    client_id = str(uuid.uuid4())
    token = secrets.token_hex(16)
    secret = secrets.token_hex(16)
    
    return DeviceCredentials(
        client_id=client_id,
        token=token,
        secret=secret
    )


@app.post("/api/v1/groups/{group_id}/devices/{device_id}/credentials/regenerate", response_model=DeviceCredentials)
async def regenerate_credentials(group_id: str, device_id: str):
    """Regenerate device credentials"""
    import secrets
    
    client_id = str(uuid.uuid4())
    token = secrets.token_hex(16)
    secret = secrets.token_hex(16)
    
    return DeviceCredentials(
        client_id=client_id,
        token=token,
        secret=secret
    )


# ── Telemetry Routes ────────────────────────────────────────────────────────

@app.get("/api/v1/groups/{group_id}/devices/{device_id}/telemetry")
async def get_latest_telemetry(group_id: str, device_id: str):
    """Get latest telemetry data for a device"""
    return {
        "device_id": device_id,
        "group_id": group_id,
        "temperature": 28.5,
        "humidity": 65.2,
        "pressure": 1013.25,
        "last_updated": datetime.utcnow()
    }


@app.get("/api/v1/groups/{group_id}/telemetry/history")
async def get_telemetry_history(
    group_id: str,
    device_id: Optional[str] = None,
    sensor_type: Optional[str] = None,
    from_time: Optional[datetime] = None,
    to_time: Optional[datetime] = None
):
    """Query telemetry history with filtering"""
    return {
        "group_id": group_id,
        "device_id": device_id,
        "sensor_type": sensor_type,
        "data": []
    }


# ── Command Routes ─────────────────────────────────────────────────────────

@app.post("/api/v1/groups/{group_id}/devices/{device_id}/commands")
async def send_command(group_id: str, device_id: str, command: CommandPayload):
    """Send command to device (publishes to Kafka iot.commands)"""
    return {
        "status": "queued",
        "command": command.command,
        "timestamp": datetime.utcnow()
    }


# ── Dashboard Routes ────────────────────────────────────────────────────────

@app.get("/api/v1/groups/{group_id}/dashboards", response_model=List[DashboardResponse])
async def list_dashboards(group_id: str):
    """List all dashboards in a group"""
    return []


@app.post("/api/v1/groups/{group_id}/dashboards", response_model=DashboardResponse)
async def create_dashboard(group_id: str, dashboard: DashboardCreate):
    """Create a new dashboard"""
    return DashboardResponse(
        id=str(uuid.uuid4()),
        group_id=group_id,
        owner_id="user_id",
        name=dashboard.name,
        widgets=dashboard.widgets,
        created_at=datetime.utcnow()
    )


@app.get("/api/v1/groups/{group_id}/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(group_id: str, dashboard_id: str):
    """Get dashboard details"""
    return DashboardResponse(
        id=dashboard_id,
        group_id=group_id,
        owner_id="user_id",
        name="Test Dashboard",
        widgets=[],
        created_at=datetime.utcnow()
    )


@app.put("/api/v1/groups/{group_id}/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(group_id: str, dashboard_id: str, dashboard: DashboardCreate):
    """Update dashboard"""
    return DashboardResponse(
        id=dashboard_id,
        group_id=group_id,
        owner_id="user_id",
        name=dashboard.name,
        widgets=dashboard.widgets,
        created_at=datetime.utcnow()
    )


@app.delete("/api/v1/groups/{group_id}/dashboards/{dashboard_id}")
async def delete_dashboard(group_id: str, dashboard_id: str):
    """Delete dashboard"""
    return {"status": "success"}


# ── Internal Routes (Broker verification) ──────────────────────────────────

@app.post("/internal/verify-credentials")
async def verify_credentials(client_id: str, token: str, secret: str):
    """Internal endpoint for broker to verify device credentials"""
    return {
        "valid": True,
        "device_id": "ESP32_01",
        "group_id": "grp_farm_01"
    }


# ── Health check ────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
