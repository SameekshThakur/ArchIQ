"""Modernization, architecture-to-code and the Copilot."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.errors import BadRequest, NotFound
from app.mock_ai.copilot import engine
from app.mock_ai.generators import codegen, modernization
from app.mock_ai.provider import LLMRequest, get_provider
from app.schemas.common import ai_meta
from app.services.ai import narrate

router = APIRouter()


# ------------------------------------------------------------ modernization
class PlanBody(BaseModel):
    scenario: str = Field("balanced", pattern="^(aggressive|balanced|conservative)$")
    overrides: dict[str, int] | None = None  # item id -> start week override


@router.get("/modernization/scenarios", tags=["modernization"])
def mod_scenarios() -> dict:
    return dict(scenarios=modernization.scenarios())


@router.post("/modernization/plan", tags=["modernization"])
async def mod_plan(body: PlanBody) -> dict:
    p = modernization.plan(body.scenario, body.overrides)
    t = p["totals"]
    facts = dict(scenario=p["scenario_label"], waves=[w["name"] for w in p["waves"]], weeks=t["duration_weeks"], cost=t["cost_k"], value=t["value_k"], critical_path=[i["name"] for i in p["items"] if i["critical"]][:3] or [p["items"][0]["name"]])
    ai = await narrate("modernization.summary", facts, [("Schedule initiatives", "dependency-aware", 300), ("Resolve critical path", f"{len(p['critical_path'])} initiatives", 180), ("Project value", f"break-even month {t['break_even_month']}", 160)],
                       [("finding", f, f) for it in p["items"][:3] for f in it["findings"][:1]])
    return dict(p, ai=ai)


# ------------------------------------------------------------------- codegen
class CodegenBody(BaseModel):
    source: str = "Target architecture"
    name: str = Field("customer-api", min_length=2, max_length=60)
    resource: str = Field("customer", min_length=2, max_length=40)
    outputs: list[str] = Field(default_factory=lambda: ["terraform", "openapi", "fastapi", "dockerfile", "ci"])
    region: str = "westeurope"
    owner: str = "Platform Engineering"
    include_openai: bool = False
    domain: str = "Customer & Distribution"


@router.get("/codegen/templates", tags=["codegen"])
def codegen_templates() -> dict:
    return dict(outputs=[dict(id=k, label=v) for k, v in codegen.OUTPUTS.items()], regions=["westeurope", "northeurope", "uksouth", "eastus2"])


@router.post("/codegen/generate", tags=["codegen"])
async def codegen_generate(body: CodegenBody) -> dict:
    bad = [o for o in body.outputs if o not in codegen.OUTPUTS]
    if bad or not body.outputs:
        raise BadRequest(f"outputs must be a non-empty subset of {sorted(codegen.OUTPUTS)}")
    g = codegen.generate(body.source, body.name, body.resource, body.outputs, body.region, body.owner, body.include_openai, body.domain)
    ai = await narrate("codegen.summary", dict(files=len(g["files"]), name=g["name"], passed=g["passed"], total=g["total"]), [("Render templates", f"{len(body.outputs)} output types", 220), ("Validate", f"{g['total']} deployability checks", 260)],
                       [("rule", "STD-SEC-014", "Private endpoints only")])
    return dict(g, ai=ai)


@router.get("/codegen/{gen_id}", tags=["codegen"])
def codegen_get(gen_id: str) -> dict:
    g = codegen.get(gen_id)
    if not g:
        raise NotFound(f"Generation {gen_id} not found")
    return g


@router.get("/codegen/{gen_id}/download", tags=["codegen"])
def codegen_download(gen_id: str) -> Response:
    data = codegen.zip_bytes(gen_id)
    if data is None:
        raise NotFound(f"Generation {gen_id} not found")
    name = codegen.get(gen_id)["name"]
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


# ------------------------------------------------------------------- copilot
class CopilotBody(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    context: dict[str, Any] | None = None


@router.get("/copilot/suggestions", tags=["copilot"])
def copilot_suggestions() -> dict:
    return dict(items=engine.suggestions())


async def _run(body: CopilotBody) -> tuple[dict, dict]:
    res = engine.answer(body.query, body.context)
    resp = await get_provider().generate(LLMRequest(task=f"copilot.{res['intent']}", input=res["facts"]))
    meta = ai_meta(res["steps"], min(res["confidence"], resp.confidence) if res["intent"] != "unknown" else res["confidence"], res["evidence"])
    meta["summary"] = resp.text
    meta["task"] = f"copilot.{res['intent']}"
    meta["provider"] = resp.meta.get("provider", get_provider().name)
    return res, meta


def _public(res: dict) -> dict:
    return {k: v for k, v in res.items() if k != "facts"}


@router.post("/copilot/query", tags=["copilot"])
async def copilot_query(body: CopilotBody) -> dict:
    res, meta = await _run(body)
    return dict(_public(res), answer=meta["summary"], ai=meta)


@router.post("/copilot/stream", tags=["copilot"])
async def copilot_stream(body: CopilotBody):
    """SSE: `trace` (reasoning steps), `token` (answer text), `cards` (structured results), `done` (AI meta)."""
    res = engine.answer(body.query, body.context)

    async def gen():
        yield dict(event="start", data=json.dumps(dict(intent=res["intent"], entities=res["entities"], headline=res["headline"])))
        for st in res["steps"]:
            yield dict(event="trace", data=json.dumps(dict(label=st[0], detail=st[1], duration_ms=st[2])))
        text = ""
        async for tok in get_provider().stream(LLMRequest(task=f"copilot.{res['intent']}", input=res["facts"])):
            text += tok
            yield dict(event="token", data=json.dumps(dict(t=tok)))
        yield dict(event="cards", data=json.dumps(dict(cards=res["cards"], followups=res["followups"])))
        meta = ai_meta(res["steps"], res["confidence"], res["evidence"])
        meta["summary"] = text.strip()
        meta["task"] = f"copilot.{res['intent']}"
        meta["provider"] = get_provider().name
        yield dict(event="done", data=json.dumps(dict(ai=meta, intent=res["intent"])))

    return EventSourceResponse(gen())
