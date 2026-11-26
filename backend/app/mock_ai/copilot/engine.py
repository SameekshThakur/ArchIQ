"""Copilot query engine. # MOCK: lexicon + intent router over the real graph/rule engines, standing in for an LLM planner.

`answer(query)` resolves entities, routes to an intent, runs the matching analysis and returns structured
facts, result cards, reasoning steps and evidence. Prose is produced afterwards by the LLMProvider
(`copilot.<intent>` narration task), so a real model can replace the templates without touching this code.
"""

from __future__ import annotations

import difflib
import re
from collections import Counter
from functools import lru_cache

from app.mock_ai.copilot.suggestions import SUGGESTIONS
from app.mock_ai.generators import documents as docs
from app.mock_ai.generators import modernization
from app.mock_ai.graph import analysis as G
from app.mock_ai.rules import assessment, drift
from app.mock_ai.scoring import debt
from app.repositories.store import get_store

DOMAIN_ALIASES = {"policy": "Policy Admin", "policy admin": "Policy Admin", "billing": "Billing & Finance", "finance": "Billing & Finance", "customer": "Customer & Distribution", "distribution": "Customer & Distribution",
                  "analytics": "Data & Analytics", "data": "Data & Analytics", "integration": "Integration & Platform", "platform": "Integration & Platform", "corporate": "Corporate Services"}
APP_ALIASES = {"claimcenter": "GWCC", "guidewire": "GWCC", "mulesoft": "MULE", "snowflake": "SNOW", "salesforce": "SFC", "sap": "SAP", "kafka": "KAFKA", "mdm": "MDM", "azure openai": "AOAI", "claims mainframe": "CMF",
               "policy admin core": "PAC", "databricks": "DBX", "api management": "APIM", "intake portal": "CIP"}
HOSTING_WORDS = {"on-prem": "on-prem", "on prem": "on-prem", "on-premises": "on-prem", "on-premise": "on-prem", "azure": "azure", "aws": "aws", "mainframe": "mainframe", "saas": "saas"}
CRIT_WORDS = {"critical": "critical", "high-criticality": "high", "business-critical": "critical"}
OPS = {"down": "outage", "outage": "outage", "fails": "outage", "fail": "outage", "retire": "retirement", "retired": "retirement", "decommission": "retirement", "decommissioned": "retirement", "sunset": "retirement"}


# ================================================================ entity lexicon
@lru_cache
def _lexicon() -> tuple[re.Pattern, dict[str, dict]]:
    s = get_store()
    lex: dict[str, dict] = {}

    def add(alias: str, ent: dict) -> None:
        a = alias.lower().strip()
        if a and a not in lex:
            lex[a] = ent

    for a in s.apps:
        e = dict(kind="application", id=a["id"], name=a["name"])
        add(a["name"], e)
        base = re.sub(r"\s*\(.*?\)", "", a["name"])
        add(base, e)
        if len(a["key"]) >= 3 and a["key"] not in ("OBS", "COL", "FAC"):
            add(a["key"], e)
    for alias, key in APP_ALIASES.items():
        if key in s.app_by_key:
            add(alias, dict(kind="application", id=s.app_by_key[key]["id"], name=s.app_by_key[key]["name"]))
    for d in s.dbs:
        add(d["name"], dict(kind="database", id=d["id"], name=d["name"]))
    by_name: dict[str, list[dict]] = {}
    for api in s.apis:
        by_name.setdefault(api["name"], []).append(api)
    for name, versions in by_name.items():
        for api in versions:
            add(f"{name} {api['version']}", dict(kind="api", id=api["id"], name=f"{name} {api['version']}", api_name=name))
        pick = next((v for v in sorted(versions, key=lambda v: v["version"], reverse=True) if v["lifecycle"] == "active"), versions[0])
        add(name, dict(kind="api", id=pick["id"], name=f"{name} {pick['version']}", api_name=name, bare=True))
    for t, meta in s.technologies.items():
        add(t, dict(kind="technology", id=None, name=t, matches=[t], lifecycle=meta["lifecycle"]))
    stems: dict[str, list[str]] = {}
    for t in s.technologies:
        stem = re.split(r"\s+\d", t)[0].strip()
        stems.setdefault(stem, []).append(t)
    for stem, ts in stems.items():
        if len(stem) > 3:
            add(stem, dict(kind="technology", id=None, name=stem, matches=ts, lifecycle="mixed"))
    for c in s.capabilities:
        add(c["name"], dict(kind="capability", id=c["id"], name=c["name"]))
    add("fnol", dict(kind="capability", id="CAP-CLM-FNOL", name="First Notice of Loss"))
    for d in sorted({a["domain"] for a in s.apps}):
        add(d, dict(kind="domain", id=None, name=d))
    for alias, d in DOMAIN_ALIASES.items():
        add(alias, dict(kind="domain", id=None, name=d))
    for o in s.owners:
        add(o["name"], dict(kind="owner", id=o["id"], name=o["name"]))
    for a in s.apps:
        add(a["team"], dict(kind="team", id=None, name=a["team"]))
    for r in s.cloud:
        add(r["name"], dict(kind="cloud", id=r["id"], name=r["name"]))
    for w in s.workflows:
        add(w["name"], dict(kind="workflow", id=w["id"], name=w["name"]))
    for st in s.standards:
        add(st["id"], dict(kind="standard", id=st["id"], name=st["title"]))
    names = sorted(lex, key=len, reverse=True)
    pat = re.compile(r"(?<![\w-])(" + "|".join(re.escape(n) for n in names) + r")(?![\w-])", re.I)
    return pat, lex


def resolve_entities(q: str) -> list[dict]:
    pat, lex = _lexicon()
    out, seen = [], set()
    for m in pat.finditer(q):
        e = lex[m.group(1).lower()]
        k = (e["kind"], e["id"] or e["name"])
        if k in seen:
            continue
        seen.add(k)
        out.append(dict(e, text=m.group(1)))
    # drop a bare domain word when a longer entity already covers it (e.g. "Claims" inside "Claims Intake Portal")
    covered = " ".join(e["text"].lower() for e in out if e["kind"] != "domain")
    return [e for e in out if not (e["kind"] == "domain" and e["text"].lower() in covered)]


# ====================================================================== helpers
def _node(i: str, rel: str | None = None) -> dict:
    s = get_store()
    r = s.by_id.get(i)
    return dict(id=i, name=r["name"] if r else i, type=(r["_type"] if r else "unknown"), rel=rel)


def _ref(r: dict) -> dict:
    return dict(id=r["id"], type=r["_type"], name=r["name"])


def _db_users(db_id: str) -> list[tuple[str, str]]:
    s = get_store()
    out = []
    for u, _, d in s.graph.in_edges(db_id, data=True):
        if d.get("rel") in ("uses", "direct_db") and s.by_id[u]["_type"] == "application":
            out.append((u, d["rel"]))
    return sorted(set(out))


def _apps_table(apps: list[dict], extra: dict[str, dict] | None = None, columns: list[str] | None = None) -> dict:
    s = get_store()
    sc = debt.app_scores()
    cols = columns or ["name", "domain", "criticality", "hosting", "tech", "debt"]
    spec = dict(name=("Application", "ref"), domain=("Domain", "text"), criticality=("Criticality", "severity"), hosting=("Hosting", "text"), tech=("Stack", "tags"), debt=("Debt", "score"), via=("Via", "text"),
                owner=("Owner", "text"), cost=("Annual cost", "money"), users=("Users", "number"))
    rows = []
    for a in apps:
        row = dict(name=_ref(a), domain=a["domain"], criticality=a["criticality"], hosting=s.cloud_of(a), tech=a["tech"][:3], debt=sc[a["id"]]["overall"], owner=a["team"], cost=a["annual_cost_k"], users=a["users"])
        row.update((extra or {}).get(a["id"], {}))
        rows.append(row)
    return dict(type="table", columns=[dict(key=c, label=spec[c][0], kind=spec[c][1]) for c in cols], rows=rows)


def _evidence(ids: list[str], limit: int = 8) -> list[tuple[str, str, str]]:
    s = get_store()
    out = []
    for i in ids[:limit]:
        r = s.by_id.get(i)
        if r:
            out.append(("asset" if r["_type"] != "document" else "document", i, r["name"] if "name" in r else r["title"]))
    return out


def _step(label: str, detail: str, ms: int = 180) -> tuple[str, str, int]:
    return (label, detail, ms)


def _mini_graph(center: str, others: list[str], rel: str = "depends on") -> dict:
    s = get_store()
    nodes = [_node(center)] + [_node(o) for o in others[:24]]
    return dict(type="graph", nodes=[dict(id=n["id"], name=n["name"], kind=n["type"], focus=n["id"] == center) for n in nodes], edges=[dict(source=o, target=center, rel=rel) for o in others[:24]], center=center, _s=len(s.apps))


# ====================================================================== intents
def list_dependents(q: str, ents: list[dict]) -> dict:
    s = get_store()
    target = next((e for e in ents if e["kind"] in ("technology", "database", "api", "application")), None)
    domain = next((e["name"] for e in ents if e["kind"] == "domain"), None)
    cap = next((e for e in ents if e["kind"] == "capability"), None)
    if not target:
        return unknown(q, ents)
    paths, via, found = [], {}, {}

    def keep(a: dict) -> bool:
        if domain and a["domain"] != domain and not s.supports(a, "CAP-" + {"Claims": "CLM"}.get(domain, "???")):
            return False
        if cap and not s.supports(a, cap["id"]):
            return False
        return True

    steps = [_step("Resolve entities", f"{target['kind']}: {target['name']}" + (f"; filter: {domain}" if domain else "") + (f"; capability: {cap['name']}" if cap else ""))]
    if target["kind"] == "technology":
        dbs = [d for d in s.dbs if d["engine"] in target["matches"]]
        for d in dbs:
            for uid, rel in _db_users(d["id"]):
                found.setdefault(uid, []).append([_node(uid), _node(d["id"], rel)])
        for a in s.apps:
            if any(t in target["matches"] for t in a["tech"]) and a["id"] not in found:
                found[a["id"]] = [[_node(a["id"]), dict(id=f"tech:{target['name']}", name=f"{target['name']} (stack)", type="technology", rel="runs_on")]]
        steps.append(_step("Traverse graph", f"{len(dbs)} database(s) on {target['name']}; followed uses and direct_db edges to consuming applications"))
        label = target["name"]
    elif target["kind"] == "database":
        for uid, rel in _db_users(target["id"]):
            found.setdefault(uid, []).append([_node(uid), _node(target["id"], rel)])
        label = target["name"]
        steps.append(_step("Traverse graph", f"followed uses and direct_db edges into {target['name']}"))
    elif target["kind"] == "api":
        group = [s.by_id[target["id"]]]  # one version at a time: "Customer API v2" means v2 only
        for api in group:
            for c in api["consumers"]:
                found.setdefault(c, []).append([_node(c), _node(api["id"], "consumes")])
        label = target["name"]
        steps.append(_step("Traverse graph", f"followed consumes edges into {label}"))
    else:
        imp = G.impact(target["id"], "breaking_change", 3)
        for uid in imp["direct_apps"]:
            found.setdefault(uid, []).append([_node(uid), _node(target["id"], "depends_on")])
        label = target["name"]
        steps.append(_step("Traverse graph", f"computed direct dependents of {label} ({len(imp['direct_apps'])})"))
    apps = [s.by_id[i] for i in found if s.by_id[i]["_type"] == "application" and keep(s.by_id[i])]
    apps.sort(key=lambda a: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[a["criticality"]], a["name"]))
    flt = f"{domain} " if domain else ""
    if cap:
        flt += f"{cap['name']} "
    paths = [dict(label=a["name"], nodes=found[a["id"]][0]) for a in apps]
    via_col = {a["id"]: dict(via=" → ".join(n["name"] for n in found[a["id"]][0][1:])) for a in apps}
    steps.append(_step("Apply filters", f"{len(found)} dependent applications → {len(apps)} after filters"))
    crit = sum(1 for a in apps if a["criticality"] == "critical")
    note = ""
    if target["kind"] == "technology" and target.get("lifecycle") == "eol":
        note = f"{target['name']} is end-of-life."
    elif target["kind"] == "technology":
        eol = [t for t in target["matches"] if s.technologies[t]["lifecycle"] == "eol"]
        note = f"{', '.join(eol)} {'is' if len(eol) == 1 else 'are'} end-of-life." if eol else ""
    wf = [w for w in s.workflows if target["kind"] == "api" and target["id"] in w["apis"]]
    cards = [_apps_table(apps, via_col, ["name", "domain", "criticality", "via", "debt"]), dict(type="paths", title="Dependency paths", paths=paths[:12])]
    if target["id"] and apps:
        cards.append(_mini_graph(target["id"], [a["id"] for a in apps]))
    headline = f"{len(apps)} {flt}application{'s' if len(apps) != 1 else ''} depend{'s' if len(apps) == 1 else ''} on {label}"
    return dict(intent="list_dependents", headline=headline, confidence=0.94, cards=cards, steps=steps, evidence=_evidence([a["id"] for a in apps] + ([target["id"]] if target["id"] else [])),
                facts=dict(target=label, kind=target["kind"], filter=flt.strip(), count=len(apps), names=[a["name"] for a in apps], critical=crit, note=note, workflows=len(wf), top_path=" → ".join(n["name"] for n in (paths[0]["nodes"] if paths else [])),
                domains=dict(Counter(a["domain"] for a in apps))),
                followups=[f"What is the impact of changing {label}?", f"Which standards apply to {label}?", "Show the modernization plan"])


def impact_of(q: str, ents: list[dict]) -> dict:
    s = get_store()
    t = next((e for e in ents if e["kind"] in ("application", "api", "database", "cloud")), None)
    if not t:
        return unknown(q, ents)
    ql = q.lower()
    change = next((v for k, v in OPS.items() if re.search(rf"\b{k}\b", ql)), "breaking_change")
    imp = G.impact(t["id"], change, 3)
    asset = s.by_id[t["id"]]
    display = t.get("api_name") or t["name"]
    direct, indirect = len(imp["direct_apps"]), len(imp["indirect_apps"])
    wfs = len(imp["workflows"])
    top = sorted((s.by_id[a] for a in imp["direct_apps"]), key=lambda a: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[a["criticality"]], a["name"]))
    cards = [dict(type="metrics", items=[dict(label="Direct applications", value=direct, tone="danger" if direct > 10 else "warning"), dict(label="Indirect applications", value=indirect, tone="neutral"),
                                          dict(label="Workflows", value=wfs, tone="warning"), dict(label="Teams", value=len(imp["teams"]), tone="neutral"), dict(label="Risk score", value=imp["risk_score"], tone="danger" if imp["risk_score"] >= 70 else "warning")]),
             _apps_table(top[:12], None, ["name", "domain", "criticality", "owner", "debt"]),
             dict(type="graph", nodes=[dict(id=asset["id"], name=asset["name"], kind=asset["_type"], focus=True)] + [dict(id=a["id"], name=a["name"], kind="application", focus=False) for a in top[:20]],
                  edges=[dict(source=asset["id"], target=a["id"], rel="impacts") for a in top[:20]], center=asset["id"])]
    steps = [_step("Resolve entities", f"{asset['_type']}: {asset['name']}"), _step("Build impact graph", f"directed 'a change breaks b' edges, depth 3, change type {change}"),
             _step("Aggregate", f"{direct} direct and {indirect} indirect applications, {wfs} workflows, {len(imp['teams'])} teams"), _step("Score", f"risk {imp['risk_score']} ({imp['risk_rating']})")]
    headline = f"Changing {display} impacts {direct} applications and {wfs} workflows." if t["kind"] == "api" else f"{asset['name']} {'outage' if change == 'outage' else 'change'} impacts {direct} applications and {wfs} workflows."
    return dict(intent="impact_of", headline=headline, confidence=0.93, cards=cards, steps=steps, evidence=_evidence([asset["id"]] + imp["direct_apps"]),
                facts=dict(name=display, kind=t["kind"], change=change, direct=direct, indirect=indirect, workflows=wfs, teams=len(imp["teams"]), risk=imp["risk_score"], rating=imp["risk_rating"], critical=len(imp["critical_apps"]),
                           top=[a["name"] for a in top[:4]], team_names=[x["team"] for x in imp["teams"][:3]]),
                followups=[f"Which applications depend on {display}?", "Show single points of failure", "Open the full impact analysis"])


def find_assets(q: str, ents: list[dict]) -> dict:
    s = get_store()
    ql = q.lower()
    domain = next((e["name"] for e in ents if e["kind"] == "domain"), None)
    tech = next((e for e in ents if e["kind"] == "technology"), None)
    cap = next((e for e in ents if e["kind"] == "capability"), None)
    team = next((e["name"] for e in ents if e["kind"] == "team"), None)
    hosting = next((v for k, v in HOSTING_WORDS.items() if re.search(rf"(?<![\w-]){re.escape(k)}(?!\w)", ql)), None)
    crit = next((v for k, v in CRIT_WORDS.items() if k in ql), None)
    eol = bool(re.search(r"unsupported|end[- ]of[- ]life|\beol\b|obsolete|out of support|legacy", ql))
    internet = bool(re.search(r"internet|public[- ]facing|externally", ql))
    apps = list(s.apps)
    parts = []
    if domain:
        apps = [a for a in apps if a["domain"] == domain]
        parts.append(domain)
    if crit:
        apps = [a for a in apps if a["criticality"] == crit]
        parts.append(crit)
    if hosting:
        apps = [a for a in apps if a["hosting"] == hosting]
        parts.append({"azure": "Azure-hosted", "aws": "AWS-hosted", "on-prem": "on-premises", "mainframe": "mainframe", "saas": "SaaS"}[hosting])
    if tech:
        apps = [a for a in apps if any(t in tech["matches"] for t in a["tech"])]
        parts.append(f"running {tech['name']}")
    if cap:
        apps = [a for a in apps if s.supports(a, cap["id"])]
        parts.append(f"supporting {cap['name']}")
    if team:
        apps = [a for a in apps if a["team"] == team]
        parts.append(f"owned by {team}")
    if eol:
        apps = [a for a in apps if any(s.technologies.get(t, {}).get("lifecycle") == "eol" for t in a["tech"]) or a["lifecycle"] in ("eol", "extended")]
        parts.append("with end-of-life or extended-support components")
    if internet:
        apps = [a for a in apps if a["internet_facing"]]
        parts.append("internet-facing")
    apps.sort(key=lambda a: -debt.app_scores()[a["id"]]["overall"])
    desc = " ".join(parts) or "all"
    steps = [_step("Parse filters", desc), _step("Query catalog", f"{len(apps)} of {len(s.apps)} applications match")]
    cards = [_apps_table(apps[:40])]
    return dict(intent="find_assets", headline=f"{len(apps)} applications match: {desc}", confidence=0.9, cards=cards, steps=steps, evidence=_evidence([a["id"] for a in apps]),
                facts=dict(count=len(apps), desc=desc, names=[a["name"] for a in apps[:6]], domains=dict(Counter(a["domain"] for a in apps)), total=len(s.apps)),
                followups=["Which of these have the highest technical debt?", "Show the modernization plan", "Show single points of failure"])


def capabilities_of(q: str, ents: list[dict]) -> dict:
    s = get_store()
    app = next((e for e in ents if e["kind"] == "application"), None)
    cap = next((e for e in ents if e["kind"] == "capability"), None)
    if app:
        a = s.by_id[app["id"]]
        caps = [s.by_id[c] for c in a["capabilities"]]
        rows = [dict(name=dict(id=c["id"], type="capability", name=c["name"]), level=c["level"], parent=s.name(c["parent"]) if c.get("parent") else "—") for c in caps]
        return dict(intent="capabilities_of", headline=f"{a['name']} supports {len(caps)} business capabilities", confidence=0.92,
                    cards=[dict(type="table", columns=[dict(key="name", label="Capability", kind="ref"), dict(key="level", label="Level", kind="number"), dict(key="parent", label="Parent", kind="text")], rows=rows)],
                    steps=[_step("Resolve entities", a["name"]), _step("Follow supports edges", f"{len(caps)} capabilities")], evidence=_evidence([a["id"]] + [c["id"] for c in caps]),
                    facts=dict(name=a["name"], count=len(caps), caps=[c["name"] for c in caps], mode="app"), followups=[f"What is the impact of changing {a['name']}?", f"Explain {a['name']}"])
    if cap:
        apps = [a for a in s.apps if s.supports(a, cap["id"])]
        return dict(intent="capabilities_of", headline=f"{len(apps)} applications support {cap['name']}", confidence=0.92, cards=[_apps_table(apps)], steps=[_step("Resolve entities", cap["name"]), _step("Follow supports edges", f"{len(apps)} applications")],
                    evidence=_evidence([a["id"] for a in apps]), facts=dict(name=cap["name"], count=len(apps), apps=[a["name"] for a in apps[:6]], mode="cap"), followups=["Which of these are single points of failure?", "Show the modernization plan"])
    return unknown(q, ents)


def compare(q: str, ents: list[dict]) -> dict:
    s = get_store()
    apps = [s.by_id[e["id"]] for e in ents if e["kind"] == "application"][:3]
    if len(apps) < 2:
        return unknown(q, ents)
    sc = debt.app_scores()
    sp = {x["app_id"]: x for x in G.spofs()}
    rows = []

    def row(label: str, fn) -> None:
        rows.append(dict(label=label, values=[fn(a) for a in apps]))

    row("Domain", lambda a: a["domain"])
    row("Criticality", lambda a: a["criticality"])
    row("Lifecycle", lambda a: a["lifecycle"])
    row("Hosting", lambda a: s.cloud_of(a))
    row("Technology", lambda a: ", ".join(a["tech"]))
    row("Owner team", lambda a: a["team"])
    row("Users", lambda a: f"{a['users']:,}")
    row("Annual cost", lambda a: f"${a['annual_cost_k']:,}k")
    row("Technical debt", lambda a: str(sc[a["id"]]["overall"]))
    row("Direct dependents", lambda a: str(len(G.impact(a["id"], "breaking_change", 1)["direct_apps"])))
    row("Single point of failure", lambda a: "Yes" if a["id"] in sp else "No")
    shared = set.intersection(*[{d for d in s.graph.successors(a["id"]) if s.graph.nodes[d].get("type") == "database"} for a in apps])
    return dict(intent="compare", headline=f"{' vs '.join(a['name'] for a in apps)}", confidence=0.9,
                cards=[dict(type="compare", columns=[dict(id=a["id"], name=a["name"]) for a in apps], rows=rows)], steps=[_step("Resolve entities", ", ".join(a["name"] for a in apps)), _step("Collect attributes", f"{len(rows)} dimensions")],
                evidence=_evidence([a["id"] for a in apps]), facts=dict(names=[a["name"] for a in apps], debts=[sc[a["id"]]["overall"] for a in apps], highest=max(apps, key=lambda a: sc[a["id"]]["overall"])["name"],
                                                                          shared=[s.name(d) for d in shared], hosting=[s.cloud_of(a) for a in apps]),
                followups=[f"What is the impact of changing {apps[0]['name']}?", "Show the biggest risks"])


def explain(q: str, ents: list[dict]) -> dict:
    s = get_store()
    t = next((e for e in ents if e["kind"] in ("application", "api", "database", "cloud", "workflow", "standard")), None)
    if not t:
        return unknown(q, ents)
    if t["kind"] == "standard":
        return standard(q, ents)
    r = s.by_id[t["id"]]
    if t["kind"] == "application":
        sc = debt.app_scores()[r["id"]]
        imp = G.impact(r["id"], "outage", 1)
        out_e = [d for _, d, k in s.graph.out_edges(r["id"], keys=True) if s.graph.edges[r["id"], d, k].get("rel") in ("integrates", "direct_db", "uses")]
        finds = [f for f in assessment.findings() if any(x["id"] == r["id"] for x in f["affected"])]
        dr = [d for d in drift.items() if d["app_id"] == r["id"] and d["status"] == "open"]
        mentions = [d for d in docs.list_documents() if d["conflicts"] and r["name"] in next(x["text"] for x in docs._all_docs() if x["id"] == d["id"])][:3]
        rows = [("Domain", r["domain"]), ("Owner", f"{s.owner(r['owner_id'])['name']} · {r['team']}"), ("Criticality", r["criticality"]), ("Lifecycle", r["lifecycle"]), ("Hosting", s.cloud_of(r)),
                ("Stack", ", ".join(r["tech"])), ("Users", f"{r['users']:,}"), ("Annual cost", f"${r['annual_cost_k']:,}k"), ("Technical debt", f"{sc['overall']} / 100"), ("Direct dependents", str(len(imp['direct_apps']))),
                ("Open findings", str(len(finds))), ("Open drift items", str(len(dr)))]
        cards = [dict(type="kv", title=r["name"], rows=[dict(label=a, value=b) for a, b in rows]), dict(type="bullets", title="Why it matters", items=sc["why"]["legacy"][:2] + sc["why"]["security"][:1] + sc["why"]["resilience"][:1] + sc["why"]["maintainability"][:1])]
        facts = dict(name=r["name"], kind="application", domain=r["domain"], criticality=r["criticality"], hosting=s.cloud_of(r), tech=r["tech"], debt=sc["overall"], dependents=len(imp["direct_apps"]), findings=len(finds), drift=len(dr), caps=[s.name(c) for c in r["capabilities"]],
                     description=r["description"], integrations=len(out_e), team=r["team"], why=sc["why"]["legacy"][:1] + sc["why"]["security"][:1], conflicts=len(mentions))
        eids = [r["id"]] + r["capabilities"]
    elif t["kind"] == "api":
        wf = [w for w in s.workflows if r["id"] in w["apis"]]
        cards = [dict(type="kv", title=r["name"] + " " + r["version"], rows=[dict(label="Protocol", value=r["protocol"]), dict(label="Lifecycle", value=r["lifecycle"]), dict(label="Exposed by", value=s.name(r["exposed_by"])), dict(label="Gateway", value=r["gateway"]),
                                                                           dict(label="Consumers", value=str(len(r["consumers"]))), dict(label="Workflows", value=str(len(wf))), dict(label="Requests/day", value=f"{r['requests_per_day']:,}")])]
        facts = dict(name=r["name"], kind="api", version=r["version"], lifecycle=r["lifecycle"], exposed_by=s.name(r["exposed_by"]), consumers=len(r["consumers"]), workflows=len(wf), protocol=r["protocol"], gateway=r["gateway"])
        eids = [r["id"], r["exposed_by"]]
    elif t["kind"] == "database":
        users = _db_users(r["id"])
        cards = [dict(type="kv", title=r["name"], rows=[dict(label="Engine", value=r["engine"]), dict(label="Hosting", value=r["hosting"]), dict(label="Size", value=f"{r['size_gb']:,} GB"), dict(label="Classification", value=r["classification"]),
                                                       dict(label="Lifecycle", value=r["lifecycle"]), dict(label="Consuming applications", value=str(len(users)))]), _apps_table([s.by_id[u] for u, _ in users], {u: dict(via=rel.replace("_", " ")) for u, rel in users}, ["name", "domain", "criticality", "via"])]
        facts = dict(name=r["name"], kind="database", engine=r["engine"], lifecycle=r["lifecycle"], users=len(users), classification=r["classification"], size=r["size_gb"], direct=sum(1 for _, k in users if k == "direct_db"))
        eids = [r["id"]] + [u for u, _ in users]
    elif t["kind"] == "cloud":
        d = next((x for x in drift.items() if x["resource"]["id"] == r["id"]), None)
        cards = [dict(type="kv", title=r["name"], rows=[dict(label="Type", value=r["type"]), dict(label="Region", value=r["region"]), dict(label="Environment", value=r["env"]), dict(label="Managed by", value=r["managed_by"]), dict(label="Drift", value=d["summary"] if d else "In sync with approved IaC")])]
        facts = dict(name=r["name"], kind="cloud", type=r["type"], region=r["region"], env=r["env"], drift=d["summary"] if d else "")
        eids = [r["id"]]
    else:
        cards = [dict(type="bullets", title="Steps", items=[f"{i + 1}. {s.name(st['app_id'])}" for i, st in enumerate(r["steps"])])]
        facts = dict(name=r["name"], kind="workflow", steps=len(r["steps"]), domain=r["domain"], volume=r["volume_per_day"])
        eids = [r["id"]] + r["apps"]
    return dict(intent="explain", headline=r["name"], confidence=0.91, cards=cards, steps=[_step("Resolve entities", r["name"]), _step("Collect attributes, scores and findings", "catalog, debt model, assessment rules, drift")], evidence=_evidence(eids), facts=facts,
                followups=[f"What is the impact of changing {r['name']}?", f"Which applications depend on {r['name']}?" if t["kind"] != "workflow" else "Show single points of failure", "Show the biggest risks"])


def risk_summary(q: str, ents: list[dict]) -> dict:
    s = get_store()
    fs = [f for f in assessment.findings() if f["severity"] == "critical"][:5]
    sp = G.spofs()[:5]
    top_debt = sorted(debt.app_scores().values(), key=lambda x: -x["overall"])[:5]
    dr = [d for d in drift.items() if d["severity"] == "critical" and d["status"] == "open"]
    rows = [dict(kind="Finding", name=f["title"], severity=f["severity"], ref=dict(id=f["id"], type="finding", name=f["id"])) for f in fs]
    rows += [dict(kind="Single point of failure", name=f"{x['name']}: {x['reasons'][0]}", severity="critical" if x["score"] >= 70 else "high", ref=dict(id=x["app_id"], type="application", name=x["name"])) for x in sp[:3]]
    rows += [dict(kind="Configuration drift", name=d["summary"], severity=d["severity"], ref=dict(id=d["id"], type="drift", name=d["id"])) for d in dr[:2]]
    cards = [dict(type="metrics", items=[dict(label="Estate debt", value=debt.estate_overall(), tone="warning"), dict(label="Critical findings", value=len([f for f in assessment.findings() if f["severity"] == "critical"]), tone="danger"),
                                          dict(label="Single points of failure", value=len(G.spofs()), tone="warning"), dict(label="Open critical drift", value=len(dr), tone="danger")]),
             dict(type="table", columns=[dict(key="kind", label="Type", kind="text"), dict(key="name", label="Risk", kind="text"), dict(key="severity", label="Severity", kind="severity"), dict(key="ref", label="Open", kind="ref")], rows=rows)]
    return dict(intent="risk_summary", headline="Top architecture risks across the estate", confidence=0.9, cards=cards,
                steps=[_step("Rank findings", "critical severity first"), _step("Rank single points of failure", "articulation points and betweenness"), _step("Check drift", f"{len(dr)} critical items open")], evidence=_evidence([x["app_id"] for x in sp]),
                facts=dict(debt=debt.estate_overall(), critical=len([f for f in assessment.findings() if f["severity"] == "critical"]), spofs=len(G.spofs()), drift=len(dr), top_finding=fs[0]["title"] if fs else "", top_spof=sp[0]["name"] if sp else "",
                           top_debt=top_debt[0]["name"]), followups=["Show single points of failure", "What has drifted from the approved design?", "Show the modernization plan"])


def spof(q: str, ents: list[dict]) -> dict:
    sp = G.spofs()
    rows = [dict(name=dict(id=x["app_id"], type="application", name=x["name"]), domain=x["domain"], criticality=x["criticality"], score=x["score"], reason=x["reasons"][0]) for x in sp]
    return dict(intent="spof", headline=f"{len(sp)} single points of failure", confidence=0.92,
                cards=[dict(type="table", columns=[dict(key="name", label="Application", kind="ref"), dict(key="domain", label="Domain", kind="text"), dict(key="criticality", label="Criticality", kind="severity"), dict(key="score", label="Score", kind="score"), dict(key="reason", label="Why", kind="text")], rows=rows)],
                steps=[_step("Find articulation points", "undirected application coupling graph"), _step("Check redundancy", "single instance, DR tier"), _step("Betweenness", "≥ 8% of shortest paths")], evidence=_evidence([x["app_id"] for x in sp]),
                facts=dict(count=len(sp), names=[x["name"] for x in sp], top=sp[0]["name"], top_reason=sp[0]["reasons"][0]), followups=[f"What is the impact of {sp[0]['name']} going down?", "Show the biggest risks"])


def stats(q: str, ents: list[dict]) -> dict:
    s = get_store()
    ql = q.lower()
    direct = sum(1 for i in s.integrations if i["style"] == "direct_db")
    table = [("applications", len(s.apps)), ("APIs", len(s.apis)), ("databases", len(s.dbs)), ("integrations", len(s.integrations)), ("direct database integrations", direct), ("cloud resources", len(s.cloud)), ("business capabilities", len(s.capabilities)),
             ("documents", len(s.documents)), ("standards", len(s.standards)), ("workflows", len(s.workflows))]
    pick = None
    if "direct" in ql and ("db" in ql or "database" in ql):
        pick = ("direct database integrations", direct)
    else:
        for label, n in table:
            if label.split()[0].lower().rstrip("s") in ql or label.lower() in ql:
                pick = (label, n)
                break
    cards = [dict(type="metrics", items=[dict(label=l.capitalize(), value=n, tone="danger" if "direct" in l else "neutral") for l, n in table[:8]])]
    headline = f"There are {pick[1]} {pick[0]}" if pick else "Estate inventory"
    if pick and pick[0] == "direct database integrations":
        headline = f"{direct} direct DB integrations should move behind APIs/events"
    return dict(intent="stats", headline=headline, confidence=0.97, cards=cards, steps=[_step("Count entities", "seeded catalog")], evidence=[], facts=dict(label=pick[0] if pick else "", n=pick[1] if pick else 0, direct=direct, table=table),
                followups=["Which applications use direct database integrations?", "Show the biggest risks"])


def direct_db(q: str, ents: list[dict]) -> dict:
    s = get_store()
    ints = [i for i in s.integrations if i["style"] == "direct_db"]
    rows = [dict(source=dict(id=i["source_id"], type=s.by_id[i["source_id"]]["_type"], name=s.name(i["source_id"])), target=dict(id=i["target_id"], type="database", name=s.name(i["target_id"])), domain=s.by_id[i["source_id"]].get("domain", "—"), criticality=i["criticality"]) for i in ints]
    by_db = Counter(s.name(i["target_id"]) for i in ints)
    return dict(intent="direct_db", headline=f"{len(ints)} direct DB integrations should move behind APIs/events", confidence=0.95,
                cards=[dict(type="table", columns=[dict(key="source", label="Consumer", kind="ref"), dict(key="target", label="Database", kind="ref"), dict(key="domain", label="Domain", kind="text"), dict(key="criticality", label="Criticality", kind="severity")], rows=rows)],
                steps=[_step("Filter integrations", "style = direct_db"), _step("Group by datastore", f"{len(by_db)} databases")], evidence=_evidence([i["source_id"] for i in ints]),
                facts=dict(count=len(ints), dbs=len(by_db), top_db=by_db.most_common(1)[0][0], top_n=by_db.most_common(1)[0][1]), followups=["Show the modernization plan", "Which applications depend on Oracle 12c?"])


def path(q: str, ents: list[dict]) -> dict:
    s = get_store()
    es = [e for e in ents if e["kind"] in ("application", "database", "api")]
    if len(es) < 2:
        return unknown(q, ents)
    a, b = es[0], es[1]
    chain = G.story_chain()
    ids = [c["id"] for c in chain]
    if a["id"] in ids and b["id"] in ids:
        i, j = ids.index(a["id"]), ids.index(b["id"])
        seg = chain[min(i, j): max(i, j) + 1]
        if i > j:
            seg = seg[::-1]
        nodes = [dict(id=c["id"], name=c["name"], type="application", rel=(c["style"] if k else None), payload=c.get("payload")) for k, c in enumerate(seg)]
        story = True
    else:
        p = G.shortest_path(a["id"], b["id"])
        nodes = [dict(n) for n in p] if p else []
        story = False
    if not nodes:
        return dict(intent="path", headline=f"No dependency path found between {a['name']} and {b['name']}", confidence=0.7, cards=[], steps=[_step("Search graph", "no path")], evidence=[], facts=dict(a=a["name"], b=b["name"], hops=0, found=False), followups=["Show the SAP to Snowflake data flow"])
    return dict(intent="path", headline=f"{a['name']} reaches {b['name']} in {len(nodes) - 1} hops", confidence=0.93, cards=[dict(type="paths", title="Data flow", paths=[dict(label=f"{nodes[0]['name']} → {nodes[-1]['name']}", nodes=nodes)])],
                steps=[_step("Resolve endpoints", f"{a['name']}, {b['name']}"), _step("Trace integrations", "story chain" if story else "shortest path in the coupling graph")], evidence=_evidence([n["id"] for n in nodes]),
                facts=dict(a=a["name"], b=b["name"], hops=len(nodes) - 1, found=True, via=[n["name"] for n in nodes[1:-1]], styles=[n.get("rel") for n in nodes[1:] if n.get("rel")], story=story),
                followups=[f"What is the impact of changing {nodes[1]['name'] if len(nodes) > 2 else a['name']}?", "Show single points of failure"])


def owner(q: str, ents: list[dict]) -> dict:
    s = get_store()
    t = next((e for e in ents if e["kind"] in ("application", "api", "database", "cloud")), None)
    if not t:
        return unknown(q, ents)
    r = s.by_id[t["id"]]
    if r["_type"] == "application":
        o, team = s.owner(r["owner_id"]), r["team"]
    elif r["_type"] == "api":
        o = s.owner(r["owner_id"])
        team = o["team"]
    elif r["_type"] == "database":
        o = s.owner(s.by_id[r["owner_app"]]["owner_id"])
        team = o["team"]
    else:
        team = r["tags"].get("owner", "—")
        o = dict(id="", name=team, team=team)
    owned = [a for a in s.apps if a["team"] == team]
    return dict(intent="owner", headline=f"{r['name']} is owned by {o['name']} ({team})", confidence=0.95, cards=[dict(type="kv", title="Ownership", rows=[dict(label="Owner", value=o["name"]), dict(label="Team", value=team), dict(label="Applications owned by team", value=str(len(owned)))]), _apps_table(owned[:10], None, ["name", "criticality", "debt"])],
                steps=[_step("Resolve entities", r["name"]), _step("Follow owned_by edge", o["name"])], evidence=_evidence([r["id"], o.get("id", "")]), facts=dict(name=r["name"], owner=o["name"], team=team, n=len(owned)), followups=[f"Explain {r['name']}", f"What is the impact of changing {r['name']}?"])


def duplication(q: str, ents: list[dict]) -> dict:
    s = get_store()
    cm = [s.app_by_key[k] for k in ("SFC", "MDM", "CIS") if k in s.app_by_key] or s.apps[:3]
    cf = next((c for c in docs.conflicts() if c["rel"] == "system_of_record"), None)
    return dict(intent="duplication", headline="3 systems act as the customer master", confidence=0.93,
                cards=[_apps_table(cm, None, ["name", "domain", "criticality", "hosting", "debt"]), dict(type="bullets", title="Documentation conflict", items=[f"{c['value']}: {c['status'].lower()} document, reviewed {c['updated_at']}" for c in cf["claims"]] if cf else [])],
                steps=[_step("Match rule R-DUP-001", "overlapping capability 'Customer Master Data'"), _step("Cross-check documents", f"{len(cf['claims']) if cf else 0} conflicting claims")], evidence=_evidence([a["id"] for a in cm]),
                facts=dict(names=[a["name"] for a in cm], recommended=cf["recommended"] if cf else "Customer Master (MDM)"), followups=["Show document conflicts", "Show the modernization plan"])


def drift_q(q: str, ents: list[dict]) -> dict:
    items = drift.items()
    open_ = [d for d in items if d["status"] == "open"]
    rows = [dict(id=dict(id=d["id"], type="drift", name=d["id"]), resource=d["resource"]["name"], summary=d["summary"], severity=d["severity"], standard=d["standard_id"]) for d in sorted(open_, key=lambda d: {"critical": 0, "high": 1, "medium": 2, "low": 3}[d["severity"]])[:12]]
    first = items[0]
    return dict(intent="drift", headline=first["summary"], confidence=0.96,
                cards=[dict(type="metrics", items=[dict(label="Drifted resources", value=len(items), tone="warning"), dict(label="Open", value=len(open_), tone="danger"), dict(label="Critical", value=len([d for d in open_ if d["severity"] == "critical"]), tone="danger")]),
                       dict(type="table", columns=[dict(key="id", label="Item", kind="ref"), dict(key="resource", label="Resource", kind="text"), dict(key="summary", label="Drift", kind="text"), dict(key="severity", label="Severity", kind="severity"), dict(key="standard", label="Standard", kind="text")], rows=rows)],
                steps=[_step("Diff approved vs deployed", f"{len(items)} resources"), _step("Map to standards", "STD-SEC-014 and others")], evidence=[("asset", first["resource"]["id"], first["resource"]["name"])],
                facts=dict(total=len(items), open=len(open_), first_summary=first["summary"], first_resource=first["resource"]["name"], standard=first["standard_id"]), followups=["Is Azure OpenAI approved?", "Show the biggest risks"])


def standard(q: str, ents: list[dict]) -> dict:
    s = get_store()
    ql = q.lower()
    st = next((s.standards_by_id[e["id"]] for e in ents if e["kind"] == "standard"), None)
    if not st and ("openai" in ql or "llm" in ql or "generative" in ql):
        st = s.standards_by_id["STD-SEC-014"]
    if not st:
        cat = Counter(x["category"] for x in s.standards)
        return dict(intent="standard", headline=f"{len(s.standards)} standards across {len(cat)} categories", confidence=0.9,
                    cards=[dict(type="metrics", items=[dict(label=k.title(), value=v, tone="neutral") for k, v in cat.items()])], steps=[_step("List standards", "policy catalogue")], evidence=[], facts=dict(count=len(s.standards), cats=dict(cat), id=None),
                    followups=["Is Azure OpenAI approved?", "What has drifted from the approved design?"])
    oai = st["id"] == "STD-SEC-014" or "openai" in ql
    headline = "Azure OpenAI is approved; direct public endpoint violates policy." if oai else f"{st['id']}: {st['title']}"
    bad = [d for d in drift.items() if d["standard_id"] == st["id"]]
    return dict(intent="standard", headline=headline, confidence=0.95,
                cards=[dict(type="kv", title=f"{st['id']} · {st['title']}", rows=[dict(label="Statement", value=st["statement"]), dict(label="Severity", value=st["severity"]), dict(label="Category", value=st["category"]), dict(label="Owner", value=st["owner"]),
                                                                                    dict(label="Remediation", value=st["remediation"]), dict(label="Open drift items", value=str(len([d for d in bad if d["status"] == "open"])))])],
                steps=[_step("Resolve standard", st["id"]), _step("Check drift register", f"{len(bad)} items reference it")], evidence=[("standard", st["id"], st["title"])] + [("asset", d["resource"]["id"], d["resource"]["name"]) for d in bad[:3]],
                facts=dict(id=st["id"], title=st["title"], statement=st["statement"], openai=oai, violations=len(bad), first=bad[0]["resource"]["name"] if bad else "", severity=st["severity"]), followups=["What has drifted from the approved design?", "Show the biggest risks"])


def cost(q: str, ents: list[dict]) -> dict:
    s = get_store()
    top = sorted(s.apps, key=lambda a: -a["annual_cost_k"])[:10]
    total = sum(a["annual_cost_k"] for a in s.apps)
    return dict(intent="cost", headline=f"Top 10 applications account for {sum(a['annual_cost_k'] for a in top) / total:.0%} of run cost", confidence=0.9, cards=[_apps_table(top, None, ["name", "domain", "cost", "debt"])],
                steps=[_step("Sort by annual run cost", f"{len(s.apps)} applications")], evidence=_evidence([a["id"] for a in top]), facts=dict(top=top[0]["name"], top_cost=top[0]["annual_cost_k"], share=round(100 * sum(a["annual_cost_k"] for a in top) / total), total=total),
                followups=["Which applications have the highest technical debt?", "Show the modernization plan"])


def debt_q(q: str, ents: list[dict]) -> dict:
    domain = next((e["name"] for e in ents if e["kind"] == "domain"), None)
    cs = debt.contributors(domain, None, 10)
    s = get_store()
    hm = debt.domain_heatmap()
    rows = [dict(name=dict(id=c["app_id"], type="application", name=c["name"]), domain=c["domain"], criticality=c["criticality"], overall=c["overall"] if "overall" in c else 0) for c in cs]
    worst = max(hm["domain_overall"].items(), key=lambda kv: kv[1])
    return dict(intent="debt", headline=f"Estate technical debt is {debt.estate_overall()} / 100; {worst[0]} is highest at {worst[1]}", confidence=0.9,
                cards=[dict(type="table", columns=[dict(key="name", label="Application", kind="ref"), dict(key="domain", label="Domain", kind="text"), dict(key="criticality", label="Criticality", kind="severity"), dict(key="overall", label="Debt", kind="score")], rows=rows)],
                steps=[_step("Score five dimensions", "legacy, security, resilience, cost, maintainability"), _step("Weight by criticality", "domain heatmap")], evidence=_evidence([c["app_id"] for c in cs]),
                facts=dict(overall=debt.estate_overall(), worst_domain=worst[0], worst_score=worst[1], top=cs[0]["name"], domain=domain), followups=["Show the modernization plan", "Show the biggest risks"])


def modernization_q(q: str, ents: list[dict]) -> dict:
    p = modernization.plan("balanced")
    wave = next((w for w in p["waves"] if re.search(rf"wave {w['id'][-1]}" if w["id"][-1].isdigit() else "$^", q.lower())), None)
    cards = [dict(type="table", columns=[dict(key="wave", label="Wave", kind="text"), dict(key="items", label="Initiatives", kind="number"), dict(key="weeks", label="Weeks", kind="text"), dict(key="cost", label="Cost", kind="money"), dict(key="risk", label="Risk", kind="severity")],
                  rows=[dict(wave=w["name"], items=len(w["items"]), weeks=f"{w['start_week']}–{w['end_week']}", cost=w["cost_k"], risk=w["risk"]) for w in p["waves"]])]
    names = [w["name"] for w in p["waves"]]
    return dict(intent="modernization", headline=" → ".join(names), confidence=0.9, cards=cards, steps=[_step("Schedule initiatives", "dependency-aware, balanced scenario")], evidence=[],
                facts=dict(waves=names, items=sum(len(w["items"]) for w in p["waves"]), weeks=p["totals"]["duration_weeks"], wave1=[i["name"] for i in p["items"] if i["wave"] == "W1"][:4]), followups=["What are the biggest risks?", "Which applications depend on Oracle 12c?"])


def documents_q(q: str, ents: list[dict]) -> dict:
    app = next((e for e in ents if e["kind"] == "application"), None)
    if app:
        gp = [g for g in docs.gaps() if g.get("app_id") == app["id"]]
        cf = [c for c in docs.conflicts() if c["subject_id"] == app["id"]]
        head = gp[0]["title"] if gp else f"{app['name']} has no documentation gaps"
        cards = [dict(type="table", columns=[dict(key="id", label="ID", kind="text"), dict(key="title", label="Gap", kind="text"), dict(key="detail", label="Detail", kind="text"), dict(key="severity", label="Severity", kind="severity")],
                      rows=[dict(id=g["id"], title=g["title"], detail=g["detail"], severity=g["severity"]) for g in gp])] if gp else []
        cards += [dict(type="table", columns=[dict(key="id", label="ID", kind="text"), dict(key="title", label="Conflict", kind="text"), dict(key="recommended", label="Recommended", kind="text"), dict(key="severity", label="Severity", kind="severity")],
                      rows=[dict(id=c["id"], title=c["title"], recommended=c["recommended"], severity=c["severity"]) for c in cf])] if cf else []
        return dict(intent="documents", headline=head, confidence=0.92, cards=cards, steps=[_step("Extract relations from documents", f"{len(docs.relations())} relations"), _step("Diff against the estate graph", app["name"])],
                    evidence=[("asset", app["id"], app["name"])], facts=dict(documents=len(docs._all_docs()), conflicts=len(cf), gaps=len(gp), coverage=docs.coverage()["by_app"].get(app["id"], 0), top_gap=head, hits=[], app=app["name"]),
                    followups=[f"What is the impact of changing {app['name']}?", "Show document conflicts and gaps"])
    sm = docs.summary()
    cf = docs.conflicts()
    gp = docs.gaps()
    hits = docs.search(q, 5) if not re.search(r"conflict|gap|undocumented|stale|coverage", q.lower()) else []
    rows = [dict(id=c["id"], title=c["title"], recommended=c["recommended"], severity=c["severity"]) for c in cf]
    return dict(intent="documents", headline=f"{sm['conflicts']} documentation conflicts and {sm['gaps']} gaps across {sm['documents']} documents", confidence=0.9,
                cards=[dict(type="metrics", items=[dict(label="Documents", value=sm["documents"], tone="neutral"), dict(label="Conflicts", value=sm["conflicts"], tone="warning"), dict(label="Gaps", value=sm["gaps"], tone="warning"), dict(label="Coverage", value=f"{sm['coverage']}%", tone="neutral")]),
                       dict(type="table", columns=[dict(key="id", label="ID", kind="text"), dict(key="title", label="Conflict", kind="text"), dict(key="recommended", label="Recommended", kind="text"), dict(key="severity", label="Severity", kind="severity")], rows=rows)],
                steps=[_step("Extract entities and relations", f"{sm['relations']} relations"), _step("Compare claims across documents", f"{sm['conflicts']} conflicts"), _step("Diff against the estate graph", f"{sm['gaps']} gaps")], evidence=[("document", h["id"], h["title"]) for h in hits],
                facts=dict(documents=sm["documents"], conflicts=sm["conflicts"], gaps=sm["gaps"], coverage=sm["coverage"], top_gap=gp[0]["title"] if gp else "", hits=[h["title"] for h in hits]), followups=["Why is Policy Admin Core undocumented?", "Show the biggest risks"])


def help_q(q: str, ents: list[dict]) -> dict:
    return dict(intent="help", headline="Ask about dependencies, impact, risk, standards, drift or modernization", confidence=0.95,
                cards=[dict(type="bullets", title="Try asking", items=SUGGESTIONS[:8])], steps=[_step("Read capabilities", "15 modules")], evidence=[], facts=dict(n=len(SUGGESTIONS)), followups=SUGGESTIONS[:3])


def unknown(q: str, ents: list[dict]) -> dict:
    near = difflib.get_close_matches(q, SUGGESTIONS, n=3, cutoff=0.2) or SUGGESTIONS[:3]
    return dict(intent="unknown", headline="I couldn't map that to the architecture graph", confidence=0.35,
                cards=[dict(type="bullets", title="Did you mean", items=near)], steps=[_step("Resolve entities", ", ".join(e["name"] for e in ents) or "none recognised"), _step("Route intent", "no confident match")], evidence=[],
                facts=dict(entities=[e["name"] for e in ents], query=q), followups=near)


# ======================================================================= router
def route(q: str, ents: list[dict]) -> str:
    ql = q.lower()
    kinds = {e["kind"] for e in ents}
    has_asset = bool(kinds & {"application", "api", "database", "cloud"})
    if re.search(r"what can you|help\b|what do you do|how do i use", ql):
        return "help"
    if re.search(r"std-|standard|polic(y|ies)(?! admin)|approved\b.*(openai|llm)|(openai|llm).*approved|violat", ql) and "drift" not in ql and "depend" not in ql:
        return "standard"
    if re.search(r"drift|deviat|differs? from (the )?approved|deployed (environment|config)|approved design", ql):
        return "drift"
    if re.search(r"direct (db|database)", ql) and not re.search(r"depend|impact", ql):
        return "direct_db"
    if re.search(r"how many|number of|count of", ql) and not has_asset:
        return "stats"
    if re.search(r"customer master|system of record|duplicate|overlap|redundant", ql) and not re.search(r"conflict|document", ql):
        return "duplication"
    if re.search(r"undocumented|not documented|documentation gap", ql):
        return "documents"
    if re.search(r"conflict|documentation|coverage|stale|gaps?\b|document", ql) and not has_asset:
        return "documents"
    if re.search(r"single point|spof|single-point", ql) and not re.search(r"impact|breaks?", ql):
        return "spof"
    if re.search(r"\bcompare\b|\bvs\.?\b|versus|difference between", ql) and len([e for e in ents if e["kind"] == "application"]) >= 2:
        return "compare"
    if re.search(r"\b(path|route|flow|reach(es)?|connect(s|ed)?|get from)\b|from .+ to ", ql) and len([e for e in ents if e["kind"] in ("application", "database")]) >= 2:
        return "path"
    if re.search(r"who owns|owner of|owned by|which team (owns|runs)|ownership", ql) and has_asset:
        return "owner"
    if re.search(r"impact|affect|break|blast|ripple|changing|change to|retire|decommission|sunset|goes down|outage|if .+ (fails?|is down)", ql) and has_asset:
        return "impact_of"
    if re.search(r"depend|rely|relies|consum|\buses?\b|\busing\b|built on|rests on|supported by", ql) and (kinds & {"technology", "database", "api", "application"}) and not re.search(r"capabilit", ql):
        return "list_dependents"
    if re.search(r"capabilit", ql) or ("support" in ql and "capability" in kinds and not (kinds & {"technology", "database"})):
        return "capabilities_of"
    if re.search(r"cost|expensive|spend|budget|run cost", ql):
        return "cost"
    if re.search(r"debt", ql):
        return "debt"
    if re.search(r"moderni[sz]|wave|roadmap|migration plan|agentif", ql):
        return "modernization"
    if re.search(r"risk|biggest|worst|top issues|concern", ql):
        return "risk_summary"
    if re.search(r"explain|what is|what's|tell me about|describe|overview of|summar", ql) and has_asset | ("workflow" in kinds):
        return "explain"
    if re.search(r"\b(list|show|which|what|find|all)\b", ql) and re.search(r"app|system|service|platform", ql):
        return "find_assets"
    if has_asset:
        return "explain"
    return "unknown"


HANDLERS = dict(list_dependents=list_dependents, impact_of=impact_of, find_assets=find_assets, capabilities_of=capabilities_of, compare=compare, explain=explain, risk_summary=risk_summary, spof=spof, stats=stats,
                direct_db=direct_db, path=path, owner=owner, duplication=duplication, drift=drift_q, standard=standard, cost=cost, debt=debt_q, modernization=modernization_q, documents=documents_q, help=help_q, unknown=unknown)


def answer(query: str, context: dict | None = None) -> dict:
    q = " ".join(query.split())
    ents = resolve_entities(q)
    focus = (context or {}).get("focus")
    if not any(e["kind"] in ("application", "api", "database", "cloud") for e in ents) and focus and re.search(r"\b(it|this|that|its)\b", q.lower()):
        r = get_store().by_id.get(focus)
        if r and r["_type"] in ("application", "api", "database", "cloud"):
            ents.insert(0, dict(kind=r["_type"], id=r["id"], name=r["name"], text="it"))
    intent = route(q, ents)
    res = HANDLERS[intent](q, ents)
    res.update(query=q, entities=[dict(kind=e["kind"], id=e["id"], name=e["name"]) for e in ents])
    for c in res["cards"]:
        c.pop("_s", None)
    return res


def suggestions() -> list[str]:
    return SUGGESTIONS
