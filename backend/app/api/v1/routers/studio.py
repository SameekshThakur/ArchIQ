"""Blueprint Intelligence Studio: requirements to a validated, governance-ready target architecture."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.mock_ai.generators import studio_catalog as cat
from app.mock_ai.rules import studio as engine
from app.repositories.store import get_store
from app.services import studio as svc

router = APIRouter(prefix="/studio", tags=["studio"])


class CreateBody(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    title: str | None = Field(default=None, max_length=120)
    domain: str | None = Field(default=None, max_length=80)
    owner: str | None = Field(default=None, max_length=80)


class RequirementsBody(BaseModel):
    text: str = Field(min_length=20, max_length=20000)
    domain: str | None = Field(default=None, max_length=80)


class BlueprintBody(BaseModel):
    blueprint_id: str
    reason: str = Field(default="", max_length=400)


class PatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    domain: str | None = Field(default=None, max_length=80)
    owner: str | None = Field(default=None, max_length=80)
    selections: dict[str, Any] | None = None
    nfr: dict[str, Any] | None = None
    linked_apps: list[str] | None = None


class OpsBody(BaseModel):
    ops: list[dict[str, Any]] = Field(max_length=svc.MAX_OPS)


class DecisionBody(BaseModel):
    gap_id: str = Field(min_length=3, max_length=200)
    action: str
    value: Any = None
    note: str = Field(default="", max_length=600)
    alternative: int | None = None


class VersionBody(BaseModel):
    label: str = Field(default="", max_length=80)


class SubmitBody(BaseModel):
    notes: str = Field(default="", max_length=1000)
    submitter: str | None = Field(default=None, max_length=80)


@router.get("/catalog")
def catalog() -> dict:
    st = get_store()
    return dict(cat.catalog(), prop_schema=engine.prop_schema(), type_labels=engine.TYPE_LABEL, coverage_floor=engine.COVERAGE_FLOOR, domains=sorted({a["domain"] for a in st.apps}),
                apps=[dict(id=a["id"], name=a["name"], domain=a["domain"], lifecycle=a["lifecycle"]) for a in st.apps],
                nfr_fields=[dict(key="availability", label="Availability (%)", kind="number"), dict(key="rto_hours", label="Recovery time, RTO (hours)", kind="number"), dict(key="rpo_minutes", label="Data loss, RPO (minutes)", kind="number"),
                            dict(key="latency_ms", label="Latency (ms)", kind="number"), dict(key="throughput_tps", label="Throughput (per second)", kind="number"), dict(key="compliance", label="Regulations", kind="text")])


@router.get("/designs")
def list_designs() -> dict:
    rows = svc.list_designs()
    return dict(items=rows, total=len(rows))


@router.post("/designs")
async def create_design(body: CreateBody) -> dict:
    return await svc.create(body.text, body.title, body.domain, body.owner)


@router.get("/designs/{n}")
def get_design(n: int) -> dict:
    return svc.view(n)


@router.delete("/designs/{n}")
def delete_design(n: int) -> dict:
    svc.delete(n)
    return dict(removed=n)


@router.post("/designs/{n}/requirements")
async def reanalyse(n: int, body: RequirementsBody) -> dict:
    return await svc.reanalyse(n, body.text, body.domain)


@router.put("/designs/{n}/blueprint")
def choose_blueprint(n: int, body: BlueprintBody) -> dict:
    return svc.choose_blueprint(n, body.blueprint_id, body.reason)


@router.patch("/designs/{n}")
def update_design(n: int, body: PatchBody) -> dict:
    return svc.update(n, body.model_dump(exclude_unset=True))


@router.post("/designs/{n}/nfr/suggest")
def suggest_nfr(n: int) -> dict:
    return svc.suggest_nfr(n)


@router.put("/designs/{n}/ops")
def set_ops(n: int, body: OpsBody) -> dict:
    return svc.set_ops(n, body.ops)


@router.post("/designs/{n}/validate")
async def validate(n: int) -> dict:
    return await svc.validate(n)


@router.post("/designs/{n}/decisions")
def decide(n: int, body: DecisionBody) -> dict:
    return svc.decide(n, body.gap_id, body.action, body.value, body.note, body.alternative)


@router.post("/designs/{n}/versions")
def save_version(n: int, body: VersionBody) -> dict:
    return svc.save_version(n, body.label)


@router.post("/designs/{n}/versions/{vn}/restore")
def restore_version(n: int, vn: int) -> dict:
    return svc.restore_version(n, vn)


@router.get("/designs/{n}/export/document")
async def export_document(n: int) -> dict:
    return await svc.document(n)


@router.get("/designs/{n}/export/document.md")
async def download_document(n: int) -> Response:
    d = await svc.document(n)
    return Response(d["markdown"], media_type="text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{d["filename"]}"'})


@router.get("/designs/{n}/export/starter.zip")
async def download_starter(n: int) -> Response:
    data, name = await svc.starter_zip(n)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/designs/{n}/export/diagram.svg")
def download_svg(n: int) -> Response:
    body, mt, name = svc.diagram(n, "svg")
    return Response(body, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/designs/{n}/export/diagram.mmd")
def download_mermaid(n: int) -> Response:
    body, mt, name = svc.diagram(n, "mmd")
    return Response(body, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/designs/{n}/submit")
async def submit(n: int, body: SubmitBody) -> dict:
    return await svc.submit(n, body.notes, body.submitter)
