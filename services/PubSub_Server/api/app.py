"""
FastAPI application — telemetry query API.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import health, telemetry
from mongodb_layer.client import MongoDBManager

# Shared MongoDB manager instance
_mongo_manager: MongoDBManager | None = None


def create_app(mongo_manager: MongoDBManager | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        if mongo_manager:
            telemetry.mongo_manager = mongo_manager
        yield
        # Shutdown — nothing to clean up

    app = FastAPI(
        title="IoT Platform Telemetry API",
        description="Query historical and real-time sensor data from IoT devices",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow dashboard/frontend access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    app.include_router(health.router)
    app.include_router(telemetry.router)

    return app
