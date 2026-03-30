"""
Telemetry query API endpoints.

Provides HTTP endpoints for the dashboard/application layer to query
historical and latest sensor data from MongoDB.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from mongodb_layer.queries import query_device_telemetry, query_latest_telemetry

router = APIRouter(prefix="/api/v1/devices", tags=["telemetry"])

# Will be set by app.py during startup
mongo_manager = None


@router.get("/{device_id}/telemetry")
async def get_device_telemetry(
    device_id: str,
    start: str = Query(default="-1h", description="Start time (Flux duration or RFC3339)"),
    stop: str = Query(default="now()", description="Stop time"),
    fields: Optional[str] = Query(
        default=None,
        description="Comma-separated field names (e.g. 'temperature,humidity')",
    ),
    limit: int = Query(default=1000, ge=1, le=10000, description="Max records"),
    aggregate: Optional[str] = Query(
        default=None,
        description="Aggregation window (e.g. '5m', '1h')",
    ),
):
    """
    Query historical telemetry data for a device.

    Example:
        GET /api/v1/devices/ESP32_01/telemetry?start=-24h&fields=temperature,humidity&aggregate=1h
    """
    if not mongo_manager:
        raise HTTPException(status_code=503, detail="MongoDB not initialized")

    try:
        data = await query_device_telemetry(
            mongo=mongo_manager,
            device_id=device_id,
            limit=limit,
        )
        return {
            "device_id": device_id,
            "count": len(data),
            "data": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}/telemetry/latest")
async def get_latest_telemetry(device_id: str):
    """
    Get the latest telemetry reading for a device.

    Example:
        GET /api/v1/devices/ESP32_01/telemetry/latest
    """
    if not mongo_manager:
        raise HTTPException(status_code=503, detail="MongoDB not initialized")

    try:
        latest = await query_latest_telemetry(
            mongo=mongo_manager,
            device_id=device_id,
        )
        return latest
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
