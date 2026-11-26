"""Document intelligence, assessment, debt radar, change impact and drift."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.errors import BadRequest, NotFound
from app.mock_ai.generators import documents as docs
from app.mock_ai.graph import analysis as G
from app.mock_ai.rules import assessment, drift
from app.mock_ai.scoring import debt
from app.repositories.store import get_store
from app.services.ai import SEV_RANK, narrate, paginate

router = APIRouter()


# --------------------------------------------------------------- documents
class IngestBody(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=20)
    doc_type: str = "Confluence"
    domain: str = "Integration & Platform"


@router.get("/documents", tags=["documents"])
def list_documents(q: str | None = None, doc_type: str | None = None, source: str | None = None, status: str | None = None, domain: str | None = None, stale: bool | None = None,
                   conflicts: bool | None = None, page: int = 1, page_size: int = Query(100, le=200)) -> dict:
    rows = docs.list_documents()
    facets = {k: dict(Counter(r[k] for r in rows)) for k in ("doc_type", "source", "status", "domain")}
    if q:
        hits = {h["id"] for h in docs.search(q, 60)}
        rows = [r for r in rows if r["id"] in hits or q.lower() in r["title"].lower()]
    for key, val in (("doc_type", doc_type), ("source", source), ("status", status), ("domain", domain)):
        if val:
            rows = [r for r in rows if r[key] in val.split(",")]
    if stale is not None:
        rows = [r for r in rows if r["stale"] == stale]
    if conflicts:
        rows = [r for r in rows if r["conflicts"] > 0]
    out = paginate(rows, page, page_size)
    out["facets"] = facets
    return out


@router.get("/documents/summary", tags=["documents"])
async def documents_summary() -> dict:
    sm = docs.summary()
    facts = dict(documents=sm["documents"], conflicts=sm["conflicts"], gaps=sm["gaps"], coverage=sm["coverage"])
    ai = await narrate("documents.summary", facts, [("Extract entities", f"{sm['entities']} distinct assets recognised", 260), ("Extract relations", f"{sm['relations']} statements", 240), ("Compare claims", f"{sm['conflicts']} conflicts", 180),
                                                   ("Diff against estate graph", f"{sm['gaps']} gaps", 200)])
    return dict(summary=sm, coverage=docs.coverage(), ai=ai)


@router.get("/documents/conflicts", tags=["documents"])
def document_conflicts() -> dict:
    return dict(items=docs.conflicts())


@router.get("/documents/gaps", tags=["documents"])
def document_gaps(kind: str | None = None, severity: str | None = None, limit: int = 100) -> dict:
    rows = docs.gaps()
    if kind:
        rows = [g for g in rows if g["kind"] == kind]
    if severity:
        rows = [g for g in rows if g["severity"] == severity]
    return dict(items=rows[:limit], total=len(rows))


@router.get("/documents/diagram", tags=["documents"])
def document_diagram(doc_ids: str | None = None, focus: str | None = None, include_gaps: bool = True) -> dict:
    return dict(mermaid=docs.reconstruct(doc_ids.split(",") if doc_ids else None, focus, include_gaps))


@router.post("/documents/ingest", tags=["documents"])
def ingest_document(body: IngestBody) -> dict:
    return docs.ingest(body.title, body.text, body.doc_type, body.domain)


@router.delete("/documents/{doc_id}", tags=["documents"])
def delete_document(doc_id: str) -> dict:
    if not doc_id.startswith("UPL-"):
        raise BadRequest("Only uploaded documents can be removed; the seeded corpus is read-only")
    if not docs.remove_upload(doc_id):
        raise NotFound(f"Document {doc_id} not found")
    return dict(removed=doc_id)


@router.get("/documents/{doc_id}", tags=["documents"])
def get_document(doc_id: str) -> dict:
    a = docs.analyze(doc_id)
    if not a:
        raise NotFound(f"Document {doc_id} not found")
    return a


# -------------------------------------------------------------- assessment
@router.get("/assessment/summary", tags=["assessment"])
async def assessment_summary() -> dict:
    sm = assessment.summary()
    fs = sorted(assessment.findings(), key=lambda f: (SEV_RANK[f["severity"]], -f["affected_count"]))
    facts = dict(total=sm["total"], critical=sm["by_severity"].get("critical", 0), high=sm["by_severity"].get("high", 0), top=[f["title"] for f in fs[:3]])
    ai = await narrate("assessment.summary", facts, [("Run 7 rule categories", "smells, SPOFs, obsolete tech, duplication, coupling, unsupported, scalability", 420), ("Score and rank", "severity then blast radius", 150)],
                       [("finding", f["id"], f["title"]) for f in fs[:3]])
    return dict(summary=sm, ai=ai)


@router.get("/assessment/findings", tags=["assessment"])
def list_findings(category: str | None = None, severity: str | None = None, domain: str | None = None, q: str | None = None, page: int = 1, page_size: int = Query(100, le=200)) -> dict:
    rows = assessment.findings()
    facets = dict(category=dict(Counter(f["category"] for f in rows)), severity=dict(Counter(f["severity"] for f in rows)), domain=dict(Counter(d for f in rows for d in f["domains"])))
    for key, val in (("category", category), ("severity", severity)):
        if val:
            rows = [f for f in rows if f[key] in val.split(",")]
    if domain:
        rows = [f for f in rows if domain in f["domains"]]
    if q:
        rows = [f for f in rows if q.lower() in f["title"].lower()]
    rows = sorted(rows, key=lambda f: (SEV_RANK[f["severity"]], -f["affected_count"], f["id"]))
    slim = [{k: v for k, v in f.items() if k not in ("evidence", "why_it_matters")} | dict(affected=f["affected"][:6]) for f in rows]
    out = paginate(slim, page, page_size)
    out["facets"] = facets
    return out


@router.get("/assessment/findings/{finding_id}", tags=["assessment"])
async def get_finding(finding_id: str) -> dict:
    f = next((x for x in assessment.findings() if x["id"] == finding_id), None)
    if not f:
        raise NotFound(f"Finding {finding_id} not found")
    facts = dict(title=f["title"], why=f["why_it_matters"], recommendation=f["recommendation"], effort=f"{f['effort']['size']} (~{f['effort']['person_days']} person-days)")
    ai = await narrate("finding.explain", facts, [("Match rule", f["rule_id"], 120), ("Collect evidence", f"{len(f['evidence'])} items", 160)], [(e["kind"], e["id"], e["label"]) for e in f["evidence"][:8]])
    return dict(finding=f, ai=ai)


@router.post("/assessment/run", tags=["assessment"])
async def run_assessment() -> dict:
    return await assessment_summary()


# -------------------------------------------------------------------- debt
@router.get("/debt/heatmap", tags=["debt"])
def debt_heatmap() -> dict:
    return debt.domain_heatmap()


@router.get("/debt/contributors", tags=["debt"])
def debt_contributors(domain: str | None = None, dimension: str | None = None, limit: int = 15) -> dict:
    return dict(items=debt.contributors(domain, dimension, limit))


@router.get("/debt/trends", tags=["debt"])
def debt_trends(domain: str | None = None) -> dict:
    return debt.trends(domain)


@router.get("/debt/summary", tags=["debt"])
async def debt_summary() -> dict:
    hm = debt.domain_heatmap()
    tr = debt.trends()
    worst = max(hm["domain_overall"].items(), key=lambda kv: kv[1])
    top = debt.contributors(None, None, 5)
    facts = dict(overall=debt.estate_overall(), delta=round(tr["overall"][-1] - tr["overall"][0], 1), worst_domain=worst[0], worst_score=worst[1], top_apps=[c["name"] for c in top])
    ai = await narrate("debt.summary", facts, [("Score five dimensions", "legacy, security, resilience, cost, maintainability", 300), ("Weight by criticality", "domain heatmap", 140)], [("asset", c["app_id"], c["name"]) for c in top])
    return dict(overall=debt.estate_overall(), ai=ai, weights=hm["weights"])


@router.get("/debt/apps/{app_id}", tags=["debt"])
def debt_app(app_id: str) -> dict:
    sc = debt.app_scores().get(app_id)
    if not sc:
        raise NotFound(f"Application {app_id} not found")
    return sc


# ------------------------------------------------------------------ impact
@router.get("/impact/{asset_id}", tags=["impact"])
async def impact(asset_id: str, change_type: str = "breaking_change", max_hops: int = Query(3, ge=1, le=5)) -> dict:
    s = get_store()
    r = s.by_id.get(asset_id)
    if not r or r["_type"] not in ("application", "api", "database", "cloud"):
        raise NotFound(f"Impactable asset {asset_id} not found")
    if change_type not in ("breaking_change", "outage", "retirement", "schema_change", "upgrade"):
        raise BadRequest("change_type must be one of breaking_change, outage, retirement, schema_change, upgrade")
    imp = G.impact(asset_id, change_type, max_hops)
    ig = G.impact_graph()
    levels = imp["levels"]
    keep = [n for n in levels if n in s.by_id]
    nodes = [dict(id=n, name=s.by_id[n]["name"], type=s.by_id[n]["_type"], hop=levels[n], criticality=s.by_id[n].get("criticality"), domain=s.by_id[n].get("domain")) for n in keep]
    edges = [dict(source=u, target=v) for u, v in ig.subgraph(keep).edges() if levels.get(u, 99) <= levels.get(v, -1)]
    apps = [s.asset(s.by_id[a]) | dict(hop=levels.get(a)) for a in imp["direct_apps"] + imp["indirect_apps"]]
    wfs = [dict(id=w, name=s.name(w), domain=s.by_id[w]["domain"], volume_per_day=s.by_id[w]["volume_per_day"]) for w in imp["workflows"]]
    name = r.get("name")
    display = name if r["_type"] != "api" else name
    facts = dict(name=display, kind=r["_type"], change=change_type, direct=len(imp["direct_apps"]), indirect=len(imp["indirect_apps"]), workflows=len(imp["workflows"]), teams=len(imp["teams"]), risk=imp["risk_score"], rating=imp["risk_rating"],
                 critical=len(imp["critical_apps"]))
    ai = await narrate("impact.summary", facts, [("Build impact graph", "directed 'a change breaks b'", 180), ("Traverse", f"{max_hops} hops", 220), ("Score blast radius", f"{imp['risk_score']}/100", 120)], [("asset", asset_id, name)] + [("asset", a, s.name(a)) for a in imp["direct_apps"][:6]])
    headline = f"Changing {name} impacts {len(imp['direct_apps'])} applications and {len(imp['workflows'])} workflows."
    if r["_type"] == "api":
        headline = f"Changing {r['name']} impacts {len(imp['direct_apps'])} applications and {len(imp['workflows'])} workflows."
    return dict(asset=s.asset(r), change_type=change_type, headline=headline, summary=dict(direct=len(imp["direct_apps"]), indirect=len(imp["indirect_apps"]), workflows=len(imp["workflows"]), databases=len(imp["databases"]),
                                                                                     teams=len(imp["teams"]), critical_apps=len(imp["critical_apps"]), risk_score=imp["risk_score"], risk_rating=imp["risk_rating"]),
                nodes=nodes, edges=edges, applications=apps, workflows=wfs, teams=imp["teams"], capabilities=[dict(id=c, name=s.name(c)) for c in imp["capabilities"]], ai=ai)


# ------------------------------------------------------------------- drift
@router.get("/drift", tags=["drift"])
async def list_drift(status: str | None = None, severity: str | None = None, domain: str | None = None, standard: str | None = None) -> dict:
    items = drift.items()
    rows = items
    if status:
        rows = [d for d in rows if d["status"] in status.split(",")]
    if severity:
        rows = [d for d in rows if d["severity"] in severity.split(",")]
    if domain:
        rows = [d for d in rows if d["domain"] == domain]
    if standard:
        rows = [d for d in rows if d["standard_id"] == standard]
    rows = sorted(rows, key=lambda d: (SEV_RANK[d["severity"]], d["id"]))
    slim = [{k: v for k, v in d.items() if k not in ("approved_iac", "deployed_config")} for d in rows]
    open_ = [d for d in items if d["status"] == "open"]
    facts = dict(total=len(items), open=len(open_), critical=sum(1 for d in open_ if d["severity"] == "critical"), top=items[0]["summary"])
    ai = await narrate("drift.summary", facts, [("Diff approved vs deployed", f"{len(items)} resources", 260), ("Map to standards", "STD-SEC-014 and others", 140)], [("asset", items[0]["resource"]["id"], items[0]["resource"]["name"])])
    return dict(items=slim, total=len(rows), summary=dict(total=len(items), open=len(open_), critical=facts["critical"], by_domain=drift.by_domain(), by_status=dict(Counter(d["status"] for d in items))), trend=drift.trend(), ai=ai)


@router.get("/drift/{item_id}", tags=["drift"])
def get_drift(item_id: str) -> dict:
    d = drift.get(item_id)
    if not d:
        raise NotFound(f"Drift item {item_id} not found")
    return dict(item=d, remediation_preview=drift.remediation_preview(d))


class DriftAction(BaseModel):
    action: str = Field(pattern="^(ticket|exception|remediate)$")
    days: int = Field(30, ge=1, le=180)


@router.post("/drift/{item_id}/actions", tags=["drift"])
def drift_action(item_id: str, body: DriftAction) -> dict:
    d = drift.act(item_id, body.action, body.days)
    if not d:
        raise NotFound(f"Drift item {item_id} not found")
    return dict(item={k: v for k, v in d.items() if k not in ("approved_iac", "deployed_config")}, message={"ticket": f"Ticket {d['ticket']} raised", "exception": f"Exception granted until {d['exception_expires']}", "remediate": "Remediation started (simulated)"}[body.action])
