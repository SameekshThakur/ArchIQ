"""Health, overview, discovery, assets and knowledge graph."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import Counter

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.config import get_settings
from app.core.errors import BadRequest, NotFound
from app.mock_ai.generators import documents as docs
from app.mock_ai.generators import modernization
from app.mock_ai.graph import analysis as G
from app.mock_ai.provider import get_provider
from app.mock_ai.rules import assessment, drift
from app.mock_ai.rules import review as review_engine
from app.mock_ai.scoring import debt
from app.repositories import persist
from app.repositories.store import get_store
from app.schemas.common import Health
from app.services import inventory
from app.services.ai import CRIT_RANK, narrate, paginate

router = APIRouter()


# ------------------------------------------------------------------ health
@router.get("/health", response_model=Health, tags=["system"])
def health() -> Health:
    s = get_store()
    return Health(status="ok", version=get_settings().version, provider=get_provider().name, seeded_entities=s.meta["counts"])


@router.get("/ai/status", tags=["system"])
def ai_status() -> dict:
    """Which model is answering, and whether it is configured. Never returns the key."""
    from app.mock_ai import provider as prov

    st, p = get_settings(), prov.get_provider()
    return dict(
        configured=st.provider.lower(), active=p.name, model=getattr(p, "deployment", None), endpoint=st.azure_openai_endpoint or None,
        key_set=bool(st.azure_openai_api_key.get_secret_value()), note=prov.provider_note, stats=getattr(p, "stats", None),
    )


@router.post("/ai/test", tags=["system"])
async def ai_test() -> dict:
    """One tiny call to the configured model, so a wrong key or endpoint is found before a demo."""
    from app.mock_ai import provider as prov

    p = prov.get_provider()
    if not hasattr(p, "ping"):
        return dict(ok=False, active=p.name, detail=prov.provider_note or "The built-in narrator is active; there is no model to test.")
    try:
        return dict(ok=True, active=p.name, **await p.ping())
    except Exception as e:
        return dict(ok=False, active=p.name, detail=f"{type(e).__name__}: {str(e)[:300]}")


# ---------------------------------------------------------------- overview
def _nav_badges() -> dict:
    s = get_store()
    fs = assessment.findings()
    return dict(findings=sum(1 for f in fs if f["severity"] in ("critical", "high")), reviews=sum(1 for a in review_engine.all_submissions() if a["stage"] in ("ai_reviewed", "arb_scheduled", "conditions")),
                drift=sum(1 for d in drift.items() if d["status"] == "open"))


@router.get("/overview/summary", tags=["overview"])
async def overview_summary() -> dict:
    s = get_store()
    fs = assessment.findings()
    crit = [f for f in fs if f["severity"] == "critical"]
    sp = G.spofs()
    dr = drift.items()
    dopen = [d for d in dr if d["status"] == "open"]
    hm = debt.domain_heatmap()
    direct_db = sum(1 for i in s.integrations if i["style"] == "direct_db")
    cov = docs.coverage()["overall"]
    plan = modernization.plan("balanced")
    trend = debt.trends()
    apps_debt = sorted(debt.app_scores().values(), key=lambda x: -x["overall"])[:5]
    kpis = [
        dict(key="apps", label="Applications", value=len(s.apps), delta=None, tone="neutral", href="/discovery"),
        dict(key="debt", label="Estate debt", value=debt.estate_overall(), unit="/100", delta=round(trend["overall"][-1] - trend["overall"][0], 1), tone="warning", href="/debt-radar", spark=trend["overall"]),
        dict(key="critical", label="Critical findings", value=len(crit), delta=None, tone="danger", href="/assessment"),
        dict(key="spof", label="Single points of failure", value=len(sp), delta=None, tone="warning", href="/graph"),
        dict(key="drift", label="Open drift", value=len(dopen), delta=None, tone="danger", href="/drift"),
        dict(key="docs", label="Documentation coverage", value=cov, unit="%", delta=None, tone="neutral", href="/documents"),
    ]
    facts = dict(apps=len(s.apps), apis=len(s.apis), debt=debt.estate_overall(), critical=len(crit), direct_db=direct_db, spofs=len(sp), drift_open=len(dopen), coverage=cov, waves=[w["name"] for w in plan["waves"]])
    ai = await narrate("overview.briefing", facts, [("Aggregate module outputs", "assessment, debt, drift, documents", 220), ("Rank risks", "critical findings first", 140)],
                       [("finding", crit[0]["id"], crit[0]["title"])] if crit else [])
    return dict(
        enterprise=s.meta["enterprise"], reference_date=s.meta["reference_date"], kpis=kpis, nav_badges=_nav_badges(), ai=ai,
        domains=[dict(domain=d, debt=hm["domain_overall"][d], apps=sum(1 for a in s.apps if a["domain"] == d)) for d in hm["domains"]],
        top_risks=[dict(id=f["id"], title=f["title"], severity=f["severity"], category=f["category"], domain=f["domain"], affected=f["affected_count"]) for f in crit[:5]],
        top_debt=[dict(app_id=a["app_id"], name=a["name"], domain=a["domain"], overall=a["overall"]) for a in apps_debt],
        chain=G.story_chain(), waves=[dict(id=w["id"], name=w["name"], items=len(w["items"]), start_week=w["start_week"], end_week=w["end_week"], risk=w["risk"]) for w in plan["waves"]],
        activity=_activity(),
        counts=dict(apps=len(s.apps), apis=len(s.apis), databases=len(s.dbs), integrations=len(s.integrations), cloud=len(s.cloud), direct_db=direct_db),
    )


def _activity() -> list[dict]:
    dr = drift.items()
    fs = assessment.findings()
    s = get_store()
    out = [dict(kind="drift", title=dr[0]["summary"], at=dr[0]["detected_at"], ref=dict(type="drift", id=dr[0]["id"]))]
    out += [dict(kind="finding", title=f["title"], at=s.meta["reference_date"], ref=dict(type="finding", id=f["id"])) for f in fs[:2]]
    out += [dict(kind="review", title=f"{a['title']} — {a['stage'].replace('_', ' ')}", at=a["submitted_at"], ref=dict(type="review", id=a["id"])) for a in sorted(review_engine.all_submissions(), key=lambda a: a["submitted_at"], reverse=True)[:3]]
    return sorted(out, key=lambda x: x["at"], reverse=True)


# --------------------------------------------------------------- discovery
SOURCES = [
    dict(id="src-azure", name="Azure Resource Graph", kind="cloud", detail="3 subscriptions, 41 resource groups"),
    dict(id="src-aws", name="AWS Config", kind="cloud", detail="1 organisation, 2 accounts"),
    dict(id="src-cmdb", name="ServiceNow CMDB", kind="cmdb", detail="Application and CI tables"),
    dict(id="src-apim", name="Azure API Management", kind="api", detail="Gateways and products"),
    dict(id="src-mule", name="MuleSoft Anypoint Exchange", kind="api", detail="System and process APIs"),
    dict(id="src-git", name="GitHub Enterprise", kind="code", detail="212 repositories scanned"),
    dict(id="src-tf", name="Terraform state", kind="iac", detail="48 workspaces"),
    dict(id="src-purview", name="Microsoft Purview", kind="data", detail="Data catalogue and lineage"),
    dict(id="src-conf", name="Confluence and SharePoint", kind="docs", detail="Architecture spaces"),
]
_scans: dict[str, dict] = {}


def _shadow_ids() -> list[str]:
    s = get_store()
    cand = [a for a in s.apps if a["criticality"] in ("low", "medium") and a["kind"] != "platform"]
    return [a["id"] for a in sorted(cand, key=lambda a: hashlib.sha1(a["id"].encode()).hexdigest())[:6]]


def _source_counts() -> dict[str, dict]:
    s = get_store()
    shadow = set(_shadow_ids())
    azure = [r for r in s.cloud if r["provider"] == "azure"]
    aws = [r for r in s.cloud if r["provider"] == "aws"]
    return {
        "src-azure": dict(found=len(azure), new=sum(1 for r in azure if r.get("drift_meta"))),
        "src-aws": dict(found=len(aws), new=len(aws)),
        "src-cmdb": dict(found=len(s.apps) - len(shadow), new=0),
        "src-apim": dict(found=sum(1 for a in s.apis if a["gateway"]), new=0),
        "src-mule": dict(found=sum(1 for a in s.apis if not a["gateway"]), new=3),
        "src-git": dict(found=sum(1 for a in s.apps if a.get("repo")), new=len(shadow)),
        "src-tf": dict(found=len(s.cloud), new=0),
        "src-purview": dict(found=len(s.dbs), new=2),
        "src-conf": dict(found=len(s.documents), new=0),
    }


def _discovery_assets() -> list[dict]:
    s = get_store()
    shadow = set(_shadow_ids())
    rows = []
    for a in s.apps:
        rows.append(dict(id=a["id"], type="application", name=a["name"], domain=a["domain"], source="GitHub Enterprise" if a["id"] in shadow else "ServiceNow CMDB", status="shadow" if a["id"] in shadow else "known",
                         confidence=0.74 if a["id"] in shadow else 0.98))
    for d in s.dbs:
        rows.append(dict(id=d["id"], type="database", name=d["name"], domain=d["domain"], source="Microsoft Purview", status="known", confidence=0.96))
    for api in s.apis:
        rows.append(dict(id=api["id"], type="api", name=f"{api['name']} {api['version']}", domain=api["domain"], source="Azure API Management" if api["gateway"] else "MuleSoft Anypoint Exchange", status="known", confidence=0.95))
    for r in s.cloud:
        rows.append(dict(id=r["id"], type="cloud", name=r["name"], domain=r["domain"], source="Azure Resource Graph" if r["provider"] == "azure" else "AWS Config", status="drifted" if r.get("drift_meta") else "known", confidence=0.97))
    return rows


@router.get("/discovery/sources", tags=["discovery"])
def discovery_sources() -> dict:
    counts = _source_counts()
    return dict(sources=[dict(s, **counts[s["id"]]) for s in SOURCES])


@router.post("/discovery/scans", tags=["discovery"])
def start_scan() -> dict:
    sid = uuid.uuid4().hex[:8]
    _scans[sid] = dict(id=sid, status="running")
    return dict(id=sid, status="running", sources=len(SOURCES))


@router.get("/discovery/scans/{scan_id}/stream", tags=["discovery"])
async def scan_stream(scan_id: str):
    if scan_id not in _scans:
        raise NotFound(f"Scan {scan_id} not found")
    counts = _source_counts()
    fast = get_settings().ai_latency <= 0

    async def gen():
        total = 0
        for src in SOURCES:
            yield dict(event="source", data=json.dumps(dict(id=src["id"], name=src["name"], status="scanning")))
            if not fast:
                await asyncio.sleep(0.45 + (int(hashlib.sha1(src["id"].encode()).hexdigest()[:4], 16) % 60) / 100)
            c = counts[src["id"]]
            total += c["found"]
            yield dict(event="source", data=json.dumps(dict(id=src["id"], name=src["name"], status="done", **c)))
        summary = discovery_results()
        _scans[scan_id] = dict(id=scan_id, status="done", summary=summary)
        yield dict(event="done", data=json.dumps(dict(scan_id=scan_id, total_found=total, summary=summary)))

    return EventSourceResponse(gen())


@router.get("/discovery/results", tags=["discovery"])
def discovery_results() -> dict:
    s = get_store()
    assets = _discovery_assets()
    by_type = Counter(a["type"] for a in assets)
    shadow = [a for a in assets if a["status"] == "shadow"]
    return dict(total=len(assets), by_type=dict(by_type), shadow=len(shadow), drifted=sum(1 for a in assets if a["status"] == "drifted"), duplicates=3, new=sum(c["new"] for c in _source_counts().values()),
                shadow_assets=shadow, integrations=len(s.integrations))


@router.get("/discovery/assets", tags=["discovery"])
def discovery_assets(type: str | None = None, status: str | None = None, q: str | None = None, page: int = 1, page_size: int = 50) -> dict:
    rows = _discovery_assets()
    if type:
        rows = [r for r in rows if r["type"] == type]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if q:
        rows = [r for r in rows if q.lower() in r["name"].lower()]
    return paginate(rows, page, page_size)


@router.post("/discovery/summary", tags=["discovery"])
async def discovery_summary() -> dict:
    res = discovery_results()
    facts = dict(sources=len(SOURCES), assets=res["total"], by_type=[f"{n} {t}s" for t, n in res["by_type"].items()], shadow=res["shadow"], duplicates=res["duplicates"])
    return dict(ai=await narrate("discovery.summary", facts, [("Scan sources", f"{len(SOURCES)} connectors", 400), ("Reconcile identities", "name, owner and repo matching", 260), ("Flag shadow IT", "assets absent from the CMDB", 180)]))


# ------------------------------------------------------------------ assets
TYPE_ROWS = {"application": "apps", "api": "apis", "database": "dbs", "cloud": "cloud", "integration": "integrations", "capability": "capabilities", "owner": "owners"}


def _asset_rows(types: list[str]) -> list[dict]:
    s = get_store()
    rows = []
    for t in types:
        rows += [s.asset(r) for r in getattr(s, TYPE_ROWS[t])]
    return rows


@router.get("/assets", tags=["assets"])
def list_assets(q: str | None = None, type: str | None = None, domain: str | None = None, criticality: str | None = None, lifecycle: str | None = None, cloud: str | None = None, owner: str | None = None,
                sort: str = "name", order: str = "asc", page: int = 1, page_size: int = Query(50, le=500)) -> dict:
    types = [t for t in (type.split(",") if type else ["application", "api", "database", "cloud"]) if t in TYPE_ROWS]
    rows = _asset_rows(types)
    facets = {k: dict(Counter(r.get(k) for r in rows if r.get(k))) for k in ("type", "domain", "criticality", "lifecycle", "cloud")}
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["name"].lower() or ql in r["id"].lower() or any(ql in t.lower() for t in r.get("tech", []))]
    for key, val in (("domain", domain), ("criticality", criticality), ("lifecycle", lifecycle), ("cloud", cloud)):
        if val:
            rows = [r for r in rows if r.get(key) in val.split(",")]
    if owner:
        rows = [r for r in rows if r.get("owner", {}).get("team") == owner or r.get("owner", {}).get("name") == owner]
    keyf = {"name": lambda r: r["name"].lower(), "criticality": lambda r: CRIT_RANK.get(r.get("criticality"), 9), "domain": lambda r: r.get("domain") or "", "type": lambda r: r["type"]}.get(sort, lambda r: r["name"].lower())
    rows.sort(key=keyf, reverse=order == "desc")
    out = paginate(rows, page, page_size)
    out["facets"] = facets
    return out


def _neighbors(node_id: str, limit: int = 80) -> dict:
    s = get_store()
    g = s.graph
    out, inn = [], []
    for _, v, d in g.out_edges(node_id, data=True):
        out.append(dict(rel=d["rel"], style=d.get("style"), asset=s.asset(s.by_id[v])))
    for u, _, d in g.in_edges(node_id, data=True):
        inn.append(dict(rel=d["rel"], style=d.get("style"), asset=s.asset(s.by_id[u])))

    def dedupe(xs: list[dict]) -> list[dict]:
        seen, res = set(), []
        for x in xs:
            k = (x["rel"], x["asset"]["id"])
            if k not in seen:
                seen.add(k)
                res.append(x)
        return res[:limit]

    return dict(outgoing=dedupe(out), incoming=dedupe(inn))


@router.get("/assets/{asset_id}", tags=["assets"])
async def get_asset(asset_id: str) -> dict:
    s = get_store()
    r = s.by_id.get(asset_id)
    if not r or r["_type"] in ("integration", "document", "workflow"):
        if r and r["_type"] == "integration":
            return dict(asset=s.asset(r), record={k: v for k, v in r.items() if not k.startswith("_")}, neighbors=dict(outgoing=[], incoming=[]), findings=[], drift=[], documents=[], debt=None)
        raise NotFound(f"Asset {asset_id} not found")
    nb = _neighbors(asset_id)
    fs = [dict(id=f["id"], title=f["title"], severity=f["severity"], category=f["category"]) for f in assessment.findings() if any(x["id"] == asset_id for x in f["affected"])]
    dr = [dict(id=d["id"], summary=d["summary"], severity=d["severity"], status=d["status"]) for d in drift.items() if asset_id in (d["app_id"], d["resource"]["id"])]
    mentions = [dict(id=d["id"], title=d["title"], status=d["status"], updated_at=d["updated_at"]) for d in docs.list_documents() if r["name"] in next(x["text"] for x in docs._all_docs() if x["id"] == d["id"])][:8]
    sc = debt.app_scores().get(asset_id)
    imp = G.impact(asset_id, "breaking_change", 2) if r["_type"] in ("application", "api", "database") else None
    record = {k: v for k, v in r.items() if not k.startswith("_") and k not in ("text",)}
    chain = G.chain_for(asset_id) if r["_type"] in ("application", "database") else []
    return dict(asset=s.asset(r), record=record, neighbors=nb, findings=fs, drift=dr, documents=mentions, debt=sc,
                impact=dict(direct=len(imp["direct_apps"]), indirect=len(imp["indirect_apps"]), workflows=len(imp["workflows"]), risk=imp["risk_score"], rating=imp["risk_rating"]) if imp else None, chain=chain)


# ------------------------------------------------------------------- graph
@router.get("/graph", tags=["graph"])
def graph(layers: str | None = None, focus: str | None = None, hops: int = 2, limit: int = Query(900, le=2000)) -> dict:
    if focus and focus not in get_store().graph:
        raise NotFound(f"Node {focus} not found")
    return G.subgraph(layers.split(",") if layers else None, focus, hops, limit)


_VIEW_LAYERS = {"app", "api", "data", "capability", "cloud", "owner"}
_VIEW_LIMIT = 30


class GraphView(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    layers: list[str] = Field(default_factory=lambda: ["app", "data"], max_length=6)
    hops: int = Field(2, ge=1, le=3)
    color_by: str = Field("type", pattern="^(type|criticality|lifecycle)$")
    focus: str | None = Field(None, max_length=80)
    domains: list[str] = Field(default_factory=list, max_length=30)
    criticality: list[str] = Field(default_factory=list, max_length=6)
    relations: list[str] = Field(default_factory=list, max_length=20)
    collapsed: list[str] = Field(default_factory=list, max_length=30)


@router.get("/graph/views", tags=["graph"])
def graph_views() -> dict:
    return dict(items=persist.list_items("graph_view", _VIEW_LIMIT))


@router.post("/graph/views", tags=["graph"], status_code=201)
def save_graph_view(body: GraphView) -> dict:
    """Saves a named view; saving under an existing name replaces it."""
    name = body.name.strip()
    if not name:
        raise BadRequest("A view needs a name")
    bad = [x for x in body.layers if x not in _VIEW_LAYERS]
    if bad:
        raise BadRequest(f"Unknown layer: {', '.join(bad)}", details=dict(allowed=sorted(_VIEW_LAYERS)))
    existing = persist.list_items("graph_view", 500)
    for v in existing:
        if v["name"].lower() == name.lower():
            persist.delete_item("graph_view", v["id"])
    if len([v for v in existing if v["name"].lower() != name.lower()]) >= _VIEW_LIMIT:
        raise BadRequest(f"You can save up to {_VIEW_LIMIT} views. Delete one first.")
    payload = body.model_dump()
    payload["name"] = name
    vid = persist.add_item("graph_view", payload)
    return dict(id=vid, **payload)


@router.delete("/graph/views/{view_id}", tags=["graph"])
def delete_graph_view(view_id: int) -> dict:
    if not persist.delete_item("graph_view", view_id):
        raise NotFound(f"View {view_id} not found")
    return dict(deleted=view_id)


@router.get("/graph/path", tags=["graph"])
def graph_path(source: str, target: str) -> dict:
    p = G.shortest_path(source, target)
    return dict(path=p or [], hops=max(0, len(p) - 1) if p else 0, found=bool(p))


@router.get("/graph/hubs", tags=["graph"])
def graph_hubs() -> dict:
    c = G.coupling()
    return dict(hubs=c["hubs"], clusters=[[dict(id=i, name=get_store().name(i)) for i in cl] for cl in c["clusters"]], spofs=G.spofs())


@router.get("/graph/chain/{node_id}", tags=["graph"])
def graph_chain(node_id: str) -> dict:
    if node_id not in get_store().by_id:
        raise NotFound(f"Node {node_id} not found")
    return dict(chain=G.chain_for(node_id))


@router.get("/graph/story-chain", tags=["graph"])
def story_chain() -> dict:
    return dict(chain=G.story_chain())


def _bad(msg: str):  # pragma: no cover
    raise BadRequest(msg)


class ImportBody(BaseModel):
    filename: str = "inventory.csv"
    text: str = Field(min_length=10)


@router.post("/discovery/import", tags=["discovery"])
async def discovery_import(body: ImportBody) -> dict:
    """Reconcile an uploaded CMDB export against the estate. Read-only."""
    r = inventory.reconcile(body.filename, body.text)
    facts = dict(filename=r["filename"], rows=r["rows"], matched=r["matched"], conflicts=r["conflicts"], probable=r["probable"], new=r["new"], missing=len(r["missing"]),
                 missing_top=[m["name"] for m in r["missing"][:3]], fields=[f for f, _ in sorted(r["conflict_fields"].items(), key=lambda kv: -kv[1])[:3]])
    ai = await narrate("discovery.import", facts, [("Read export", f"{r['rows']} rows, columns mapped: {', '.join(r['columns'])}", 120), ("Match to estate", "normalised name, then fuzzy match", 380),
                                                  ("Compare attributes", "criticality, hosting, owner, lifecycle", 260), ("Find gaps", "estate applications absent from the export", 140)],
                       [("application", x["asset_id"], x["name"]) for x in r["items"] if x["status"] == "conflict"][:4])
    out = dict(r, ai=ai)
    out["saved_id"] = persist.add_item("import", dict(out))
    return out


@router.get("/discovery/imports", tags=["discovery"])
def list_imports() -> dict:
    items = [dict(id=i["id"], filename=i["filename"], created_at=i["created_at"], rows=i["rows"], matched=i["matched"], conflicts=i["conflicts"], new=i["new"], missing=len(i["missing"])) for i in persist.list_items("import", 10)]
    return dict(items=items, total=len(items))


@router.get("/discovery/imports/{import_id}", tags=["discovery"])
def get_import(import_id: int) -> dict:
    i = persist.get_item("import", import_id)
    if not i:
        raise NotFound(f"Import {import_id} not found")
    return dict(i, saved_id=import_id)


@router.delete("/discovery/imports/{import_id}", tags=["discovery"])
def delete_import(import_id: int) -> dict:
    if not persist.delete_item("import", import_id):
        raise NotFound(f"Import {import_id} not found")
    return dict(removed=import_id)
