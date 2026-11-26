"""The guided start: ask what the person is looking for, take their documents and domain, run the analysis end to end."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import workspace

router = APIRouter(tags=["workspace"])


class WorkspaceFile(BaseModel):
    filename: str = Field(min_length=1, max_length=260)
    text: str = Field(min_length=1)


class StartBody(BaseModel):
    intent_id: str | None = None
    intent_text: str = Field("", max_length=500)
    domain: str = Field(min_length=2, max_length=80)
    files: list[WorkspaceFile] = Field(default_factory=list, max_length=workspace.MAX_DOCS)
    connections: list[str] = Field(default_factory=list, max_length=12, description="Platform ids (for example 'servicenow') to read as part of this analysis")


@router.get("/workspace")
def get_workspace() -> dict:
    return workspace.get()


@router.get("/workspace/options")
def workspace_options() -> dict:
    return dict(intents=workspace.INTENTS, domains=workspace.known_domains(), max_files=workspace.MAX_DOCS)


@router.post("/workspace/start")
def start_workspace(body: StartBody) -> dict:
    return workspace.start(body.intent_id, body.intent_text, body.domain, [f.model_dump() for f in body.files], body.connections)


@router.post("/workspace/demo")
def load_demo() -> dict:
    return workspace.load_demo()


@router.delete("/workspace")
def reset_workspace() -> dict:
    return workspace.reset()
