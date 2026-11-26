"""Platform connections: list, configure, test, sync. All connectors are read-only towards the platform."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import connections as svc

router = APIRouter(tags=["connections"])


class ConfigBody(BaseModel):
    mode: str = "live"
    config: dict[str, Any] = Field(default_factory=dict)
    secrets: dict[str, str | None] = Field(default_factory=dict)


@router.get("/connections")
def list_connections() -> dict:
    return svc.overview()


@router.get("/connections/{pid}")
def get_connection(pid: str) -> dict:
    return svc.latest(pid)


@router.put("/connections/{pid}")
def put_connection(pid: str, body: ConfigBody) -> dict:
    return svc.configure(pid, body.mode, body.config, body.secrets)


@router.delete("/connections/{pid}")
def delete_connection(pid: str) -> dict:
    return svc.remove(pid)


@router.post("/connections/{pid}/test")
async def test_connection(pid: str) -> dict:
    return await asyncio.to_thread(svc.test, pid)


@router.post("/connections/{pid}/sync")
async def sync_connection(pid: str) -> dict:
    started = time.time()
    mode, data, error = await asyncio.to_thread(svc.fetch, pid)
    return await svc.apply(pid, mode, data, error, started)
