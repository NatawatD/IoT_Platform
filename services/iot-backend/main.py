from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import init_db
from routers import devices, groups, internal

app = FastAPI(title="IoT Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await init_db()


@app.get("/health")
async def health_check():
    return {"status": "ok"}


app.include_router(groups.router)
app.include_router(devices.router)
app.include_router(internal.router)
