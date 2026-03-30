"""
Health check endpoint.
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    """Health check — returns service status."""
    return {"status": "healthy", "service": "iot-platform-api"}
