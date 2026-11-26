"""Target architecture, decision agent, standards, review agent and blueprints."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.core.errors import BadRequest, NotFound
from app.mock_ai.generators import blueprints, design
from app.mock_ai.rules import review as review_engine
from app.mock_ai.rules import standards as std
from app.repositories import persist
from app.repositories.store import get_store
from app.services.ai import SEV_RANK, narrate

router = APIRouter()


# --------------------------------------------------------- target architecture
class OptionsBody(BaseModel):
    goals: str = Field(min_length=3, max_length=2000)
    domain: str = "Claims"
    nfr: dict[str, Any] = Field(default_factory=dict)


class EvaluateBody(BaseModel):
    nfr: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] | None = None
    options: list[dict[str, Any]] | None = None


@router.get("/target-architecture/presets", tags=["target-architecture"])
def presets() -> dict:
    return dict(presets=design.PRESETS, default_weights=design.DEFAULT_WEIGHTS)


@router.post("/target-architecture/options", tags=["target-architecture"])
async def target_options(body: OptionsBody) -> dict:
    out = design.generate_options(body.goals, body.domain, body.nfr)
    ev = design.evaluate(body.nfr, None, None)
    return dict(out, evaluation=ev, ai=await _recommendation(ev, "Generate options", f"{len(out['options'])} candidate architectures for {body.domain}"))


async def _recommendation(ev: dict, step: str, detail: str) -> dict:
    top, runner = ev["ranking"][0], ev["ranking"][1]
    names = {m["option"]: m["name"] for m in ev["matrix"]}
    crit = max(ev["weights"], key=lambda c: ev["weights"][c])
    flips = [x for x in ev.get("sensitivity", []) if x.get("flips")]
    facts = dict(winner=top["option"], winner_name=names[top["option"]], score=top["score"], runner_name=names[runner["option"]], runner_score=runner["score"],
                 top_criterion=next((c["label"] for c in ev["criteria"] if c["key"] == crit), crit), sensitive=bool(flips), sensitive_criterion=flips[0]["label"] if flips else "")
    return await narrate("design.recommendation", facts, [(step, detail, 260), ("Score against criteria", "cost, security, scalability, complexity, time to market", 300), ("Sensitivity analysis", "each weight ±50%", 220)],
                         [("rule", "criteria", "Weighted decision matrix")], confidence=ev.get("confidence"))


@router.post("/target-architecture/evaluate", tags=["target-architecture"])
async def target_evaluate(body: EvaluateBody) -> dict:
    ev = design.evaluate(body.nfr, body.weights, body.options)
    return dict(ev, ai=await _recommendation(ev, "Re-weight criteria", "user-adjusted weights"))


# ----------------------------------------------------------------- decisions
class AdrBody(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    domain: str = "Claims"
    nfr: dict[str, Any] = Field(default_factory=dict)
    weights: dict[str, float] | None = None
    chosen_option: str | None = None
    context: str | None = None


@router.get("/decisions", tags=["decisions"])
def decisions() -> dict:
    rows = design.decision_log()
    return dict(items=rows, total=len(rows), by_status=dict(Counter(r["status"] for r in rows)))


@router.post("/decisions/adr", tags=["decisions"])
async def create_adr(body: AdrBody) -> dict:
    adr = design.make_adr(body.title, body.domain, body.nfr, body.weights, body.chosen_option, body.context)
    ev = design.evaluate(body.nfr, body.weights)
    return dict(adr, ai=await _recommendation(ev, "Draft ADR", f"{adr['number']} from the decision matrix"))


@router.get("/decisions/{number}", tags=["decisions"])
def get_decision(number: str) -> dict:
    s = get_store()
    row = next((r for r in design.decision_log() if r["number"] == number), None)
    if not row:
        raise NotFound(f"Decision {number} not found")
    doc = s.by_id.get(row.get("document_id", ""))
    return dict(decision=row, markdown=doc["text"] if doc else None)


# ----------------------------------------------------------------- standards
class CheckBody(BaseModel):
    design: str | dict[str, Any]
    only: list[str] | None = None


@router.get("/standards", tags=["standards"])
def list_standards(category: str | None = None, kind: str | None = None, q: str | None = None) -> dict:
    s = get_store()
    rows = s.standards
    if category:
        rows = [r for r in rows if r["category"] in category.split(",")]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if q:
        rows = [r for r in rows if q.lower() in (r["id"] + r["title"] + r["statement"]).lower()]
    return dict(items=sorted(rows, key=lambda r: r["id"]), total=len(rows), facets=dict(category=dict(Counter(r["category"] for r in s.standards)), kind=dict(Counter(r["kind"] for r in s.standards))))


@router.get("/standards/sample-design", tags=["standards"])
def sample_design() -> dict:
    s = get_store()
    sub = next(a for a in s.arb if a["id"] == "ARB-2026-001")
    import json

    return dict(name=sub["title"], format="json", text=json.dumps(dict(name=sub["title"], components=sub["components"], nfr=sub["nfr"]), indent=2))


@router.get("/standards/{standard_id}", tags=["standards"])
def get_standard(standard_id: str) -> dict:
    r = get_store().standards_by_id.get(standard_id)
    if not r:
        raise NotFound(f"Standard {standard_id} not found")
    return r


@router.post("/standards/check", tags=["standards"])
async def check_standards(body: CheckBody) -> dict:
    if isinstance(body.design, str) and len(body.design.strip()) < 10:
        raise BadRequest("Provide a design as JSON, YAML or a few lines of text")
    parsed = std.parse_design(body.design)
    res = std.check_design(parsed, body.only)
    heads = [r["headline"] for r in res["results"] if r["status"] == "fail" and r.get("headline")]
    facts = dict(passed=res["passed"], warned=res["warned"], failed=res["failed"], components=res["components"], headlines=heads or [res["headline"]])
    ai = await narrate("standards.summary", facts, [("Parse design", f"{res['format']}, {res['components']} components", 160), ("Evaluate standards", f"{len(res['results'])} checks", 320)],
                       [("standard", r["standard_id"], r["title"]) for r in res["results"] if r["status"] != "pass"][:8])
    return dict(res, ai=ai)


# ------------------------------------------------------------------- reviews
def _row(a: dict, with_review: bool = True) -> dict:
    out = {k: a[k] for k in ("id", "title", "domain", "submitter", "stage", "submitted_at", "arb_date", "tier", "summary")}
    if with_review:
        r = review_engine.review(a)
        out.update(readiness=r["readiness"], verdict=r["verdict"], counts=r["counts"])
    return out


@router.get("/reviews", tags=["reviews"])
def list_reviews() -> dict:
    rows = [_row(a) for a in review_engine.all_submissions()]
    return dict(items=rows, total=len(rows), by_stage=dict(Counter(r["stage"] for r in rows)))


class AdhocReview(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    domain: str = "Claims"
    tier: str = Field("tier2", pattern="^tier[123]$")
    design: str | dict[str, Any]
    nfr: dict[str, Any] = Field(default_factory=dict)


def _adhoc_submission(body: AdhocReview) -> dict:
    parsed = std.parse_design(body.design)
    return dict(id="ADHOC", title=body.title, domain=body.domain, tier=body.tier, nfr=body.nfr or parsed.get("nfr", {}), components=parsed["components"], linked_apps=[], summary="Ad-hoc review", stage="draft", submitter="You",
                submitted_at="", arb_date="")


@router.post("/reviews/run", tags=["reviews"])
async def run_review(body: AdhocReview) -> dict:
    out = await _review_payload(_adhoc_submission(body))
    # saved so the review can be reopened later; the design text is kept and the result is recomputed (it is deterministic)
    out["saved_id"] = persist.add_item("review", dict(request=body.model_dump(), title=body.title, tier=body.tier, verdict=out["review"]["verdict"], readiness=out["review"]["readiness"]))
    return out


@router.get("/reviews/adhoc", tags=["reviews"])
def list_adhoc_reviews() -> dict:
    items = [{k: v for k, v in r.items() if k != "request"} for r in persist.list_items("review", 20)]
    return dict(items=items, total=len(items))


@router.get("/reviews/adhoc/{saved_id}", tags=["reviews"])
async def get_adhoc_review(saved_id: int) -> dict:
    r = persist.get_item("review", saved_id)
    if not r:
        raise NotFound(f"Saved review {saved_id} not found")
    out = await _review_payload(_adhoc_submission(AdhocReview(**r["request"])))
    out["saved_id"] = saved_id
    return out


@router.delete("/reviews/adhoc/{saved_id}", tags=["reviews"])
def delete_adhoc_review(saved_id: int) -> dict:
    if not persist.delete_item("review", saved_id):
        raise NotFound(f"Saved review {saved_id} not found")
    return dict(removed=saved_id)


async def _review_payload(sub: dict) -> dict:
    r = review_engine.review(sub)
    facts = dict(verdict=r["verdict"].replace("_", " ").upper(), title=sub["title"], readiness=r["readiness"], blockers=r["counts"].get("critical", 0) + r["counts"].get("high", 0), warnings=r["counts"].get("medium", 0) + r["counts"].get("low", 0),
                 nfr=r["nfr_coverage"]["percent"])
    ai = await narrate("review.summary", facts, [("Check standards", f"{r['standards']['passed']} passed, {r['standards']['failed']} failed", 280), ("Check NFR coverage", f"{r['nfr_coverage']['percent']}%", 140), ("Assess estate risk", "linked applications and patterns", 200)],
                       [(e["kind"], e["id"], e["label"]) for f in r["findings"][:6] for e in f["evidence"][:1]])
    return dict(review=r, submission={k: v for k, v in sub.items() if k != "components"}, components=sub["components"], ai=ai)


@router.get("/reviews/{review_id}", tags=["reviews"])
async def get_review(review_id: str) -> dict:
    sub = review_engine.get_submission(review_id)
    if not sub:
        raise NotFound(f"Submission {review_id} not found")
    return await _review_payload(sub)


# --------------------------------------------------------------- blueprints
@router.get("/blueprints", tags=["blueprints"])
def list_blueprints(category: str | None = None, q: str | None = None) -> dict:
    s = get_store()
    rows = s.patterns
    if category:
        rows = [p for p in rows if p["category"] == category]
    if q:
        rows = [p for p in rows if q.lower() in (p["name"] + p["summary"] + " ".join(p["tags"])).lower()]
    return dict(items=rows, total=len(rows), categories=sorted({p["category"] for p in s.patterns}))


@router.get("/blueprints/{pattern_id}", tags=["blueprints"])
async def get_blueprint(pattern_id: str) -> dict:
    bp = blueprints.generate(pattern_id)
    if not bp:
        raise NotFound(f"Pattern {pattern_id} not found")
    ai = await narrate("blueprint.summary", dict(name=bp["name"], when=bp["when_to_use"], components=len(bp["components"])), [("Load pattern", pattern_id, 120), ("Render diagram and starters", "Mermaid, Terraform, OpenAPI", 280)],
                       [("rule", pattern_id, bp["name"])])
    return dict(bp, ai=ai)


@router.get("/blueprints/{pattern_id}/download", tags=["blueprints"])
def download_blueprint(pattern_id: str) -> Response:
    data = blueprints.bundle_zip(pattern_id)
    if data is None:
        raise NotFound(f"Pattern {pattern_id} not found")
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{pattern_id.lower()}-blueprint.zip"'})


_ = SEV_RANK
