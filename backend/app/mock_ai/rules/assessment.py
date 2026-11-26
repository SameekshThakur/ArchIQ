"""Architecture assessment rule engine. Findings are computed from the knowledge graph and seed data."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from functools import lru_cache

from app.mock_ai.graph import analysis as A
from app.repositories.store import get_store

CATEGORIES = ["smell", "spof", "obsolete_tech", "duplication", "tight_coupling", "unsupported_component", "scalability"]
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
CRIT_W = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _ref(s, ident: str) -> dict:
    r = s.by_id[ident]
    return dict(id=ident, name=r["name"], type=r["_type"])


def _size(pd: int) -> str:
    return "S" if pd <= 15 else "M" if pd <= 60 else "L" if pd <= 180 else "XL"


def _sev_from(crits: list[str], floor: str = "medium") -> str:
    top = max((CRIT_W[c] for c in crits), default=1)
    base = {4: "high", 3: "high", 2: "medium", 1: "low"}[top]
    return base if SEV_ORDER[base] <= SEV_ORDER[floor] else floor


@lru_cache
def findings() -> list[dict]:
    s = get_store()
    raw: list[dict] = []

    def add(rule, category, severity, title, affected, evidence, recommendation, why, pd, domain=None, metrics=None, adr_hint=None):
        doms = sorted({s.by_id[a]["domain"] for a in affected if s.by_id[a].get("domain")}) or ["Integration & Platform"]
        raw.append(dict(rule_id=rule, category=category, severity=severity, title=title,
                        affected=[_ref(s, a) for a in affected[:40]], affected_count=len(affected), evidence=evidence,
                        recommendation=recommendation, why_it_matters=why, effort=dict(size=_size(pd), person_days=pd),
                        domain=domain or doms[0], domains=doms, metrics=metrics or {}, adr_hint=adr_hint or title))

    db_by_id = {d["id"]: d for d in s.dbs}
    # ---- R-DB-001: direct DB integrations (the headline insight)
    direct = [i for i in s.integrations if i["style"] == "direct_db"]
    by_db: dict[str, list[dict]] = defaultdict(list)
    for i in direct:
        by_db[i["target_id"]].append(i)
    add("R-DB-001", "smell", "critical", f"{len(direct)} direct DB integrations should move behind APIs/events",
        [i["source_id"] for i in direct if i["source_kind"] == "app"] + sorted(by_db.keys()),
        [dict(kind="integration", id=i["id"], label=i["name"]) for i in direct],
        "Expose each datastore through a system API or publish change events to Kafka, then repoint consumers. Start with the shared Policy Master DB.",
        "Direct database access couples consumers to physical schemas, bypasses authorisation and audit, and makes every schema change or platform upgrade a multi-team event.",
        sum(18 for _ in direct), metrics=dict(direct_integrations=len(direct), target_databases=len(by_db), app_sources=sum(1 for i in direct if i["source_kind"] == "app")),
        adr_hint="Replace direct database integrations with APIs and events")
    for dbid, ints in sorted(by_db.items(), key=lambda kv: -len(kv[1])):
        if len(ints) < 2:
            continue
        db = db_by_id[dbid]
        consumers = [i["source_id"] for i in ints]
        doms = sorted({s.by_id[c].get("domain") or db_by_id[c]["domain"] for c in consumers if c in s.by_id and (s.by_id[c].get("domain") or c in db_by_id)})
        add("R-DB-002", "smell", "high" if db["classification"] in ("restricted", "confidential") else "medium",
            f"{db['name']} is accessed directly by {len(ints)} consumers across {len(doms)} domains",
            consumers + [dbid], [dict(kind="integration", id=i["id"], label=i["name"]) for i in ints],
            f"Introduce a data API for {db['name']} and migrate consumers one domain at a time.",
            "A shared database that several domains write to is an unmanaged integration point: no consumer can change the schema without coordinating with all the others.",
            len(ints) * 12, domain=db["domain"], metrics=dict(consumers=len(ints), domains=len(doms), engine=db["engine"]))

    # ---- R-SPOF: single points of failure
    for sp in A.spofs()[:7]:
        app = s.by_id[sp["app_id"]]
        add("R-SPOF-001", "spof", "critical" if app["criticality"] == "critical" else "high",
            f"{app['name']} is a single point of failure", [app["id"]],
            [dict(kind="asset", id=app["id"], label=app["name"])] + [dict(kind="rule", id="R-SPOF-001", label=r) for r in sp["reasons"]],
            "Deploy active-active across zones, introduce a standby with automated failover, and rehearse recovery quarterly.",
            f"{sp['degree']} systems are coupled to it. An outage of {app['name']} stops dependent business flows across {app['domain']} and beyond.",
            45 if app["kind"] in ("legacy", "package") else 25, domain=app["domain"],
            metrics=dict(coupled_systems=sp["degree"], dr_tier=sp["dr_tier"], single_instance=sp["single_instance"]))

    # ---- R-OBS: obsolete technology (union of app stacks and database dependents)
    usage: dict[str, set[str]] = defaultdict(set)
    for a in s.apps:
        for t in a["tech"]:
            usage[t].add(a["id"])
    for db in s.dbs:
        deps = {u for u, v, d in s.graph.in_edges(db["id"], data=True) if d["rel"] in ("uses", "direct_db") and s.graph.nodes[u]["type"] == "application"}
        usage[db["engine"]] |= deps
    for tech, info in s.technologies.items():
        if info["lifecycle"] == "supported" or not usage.get(tech):
            continue
        apps = sorted(usage[tech])
        crits = [s.by_id[a]["criticality"] for a in apps]
        eol = info["lifecycle"] == "eol"
        sev = ("critical" if (len(apps) >= 5 and CRIT_W[max(crits, key=lambda c: CRIT_W[c])] >= 3) else "high") if eol else "medium"
        end = info["support_end"]
        verb = f"out of vendor support since {end}" if eol else f"in extended support until {end}"
        title = f"{tech} is {verb}; used by {len(apps)} application{'s' if len(apps) != 1 else ''}"
        add("R-OBS-001", "obsolete_tech", sev, title, apps, [dict(kind="asset", id=a, label=s.by_id[a]["name"]) for a in apps] + [dict(kind="standard", id=next((x["id"] for x in s.standards if x.get("technology") == tech), "STD-TECH"), label=f"Technology radar: {tech}")],
            f"Plan an upgrade or replacement of {tech}; track it on the modernization roadmap and block new adoption.",
            f"{tech} no longer receives security patches" + ("." if eol else " beyond the extended window.") + " Compliance and cyber-insurance obligations are harder to evidence.",
            max(15, len(apps) * 20), metrics=dict(applications=len(apps), lifecycle=info["lifecycle"], support_end=end, category=info["category"]))

    # ---- R-DUP: duplicated capabilities
    roles: dict[str, list[dict]] = defaultdict(list)
    for a in s.apps:
        if a.get("role"):
            roles[a["role"]].append(a)
    for role, apps in roles.items():
        if len(apps) < 2:
            continue
        label = role.replace("_", " ")
        add("R-DUP-001", "duplication", "high" if len(apps) >= 3 else "medium", f"{len(apps)} systems act as the {label} ({', '.join(a['name'] for a in apps)})",
            [a["id"] for a in apps], [dict(kind="asset", id=a["id"], label=a["name"]) for a in apps],
            f"Nominate one system of record for {label} data and retire or demote the others to consumers.",
            "Overlapping systems of record cause conflicting data, duplicated licence and run costs, and slow every change that touches the shared entity.",
            len(apps) * 70, metrics=dict(systems=len(apps), role=role, annual_cost_k=sum(a["annual_cost_k"] for a in apps)))

    # ---- R-COUP: tight coupling
    cp = A.coupling()
    for cl in cp["clusters"]:
        names = [s.by_id[x]["name"] for x in cl]
        add("R-COUP-001", "tight_coupling", "high", f"Cyclic dependency between {', '.join(names)}", cl,
            [dict(kind="asset", id=x, label=s.by_id[x]["name"]) for x in cl],
            "Break the cycle by introducing an event or API contract owned by one side and removing the reverse call.",
            "Systems in a dependency cycle must be changed, tested and released together, so a defect in one propagates to all of them.",
            len(cl) * 25, metrics=dict(cluster_size=len(cl)))
    for hub in cp["hubs"][:5]:
        app = s.by_id[hub["app_id"]]
        if app["kind"] in ("platform",):
            continue
        if hub["degree"] >= 20:
            add("R-COUP-002", "tight_coupling", "medium", f"{app['name']} is coupled to {hub['degree']} other applications", [app["id"]],
                [dict(kind="asset", id=app["id"], label=app["name"])], "Split the integration surface into bounded APIs and move consumers to domain events.",
                "A hub with this many neighbours has an enormous change blast radius.", 40, domain=app["domain"], metrics=dict(degree=hub["degree"], betweenness=hub["betweenness"]))

    # ---- R-UNS: unsupported components
    for a in s.apps:
        if a["lifecycle"] != "eol":
            continue
        bad = [t for t in a["tech"] if s.technologies.get(t, {}).get("lifecycle") == "eol"]
        add("R-UNS-001", "unsupported_component", "critical" if a["criticality"] in ("critical", "high") else "high",
            f"{a['name']} runs on unsupported components" + (f" ({', '.join(bad)})" if bad else ""), [a["id"]],
            [dict(kind="asset", id=a["id"], label=a["name"])] + [dict(kind="standard", id=x["id"], label=x["title"]) for x in s.standards if x.get("technology") in bad],
            "Replace or re-platform onto a supported runtime. Where that is not possible, isolate the host and apply compensating controls.",
            f"{a['vulns_critical']} critical and {a['vulns_high']} high vulnerabilities are open and cannot be patched upstream.",
            60 if a["kind"] in ("legacy", "package") else 30, domain=a["domain"], metrics=dict(critical_vulns=a["vulns_critical"], high_vulns=a["vulns_high"]))

    # ---- R-SCALE: capacity pressure and batch contention
    for a in s.apps:
        util = a["peak_tps"] / a["capacity_tps"]
        if util >= 0.78:
            add("R-SCALE-001", "scalability", "high" if util >= 0.88 else "medium", f"{a['name']} runs at {round(util * 100)}% of capacity at peak", [a["id"]],
                [dict(kind="asset", id=a["id"], label=f"peak {a['peak_tps']} tps of {a['capacity_tps']} tps")],
                "Add horizontal scaling and load-test to 2x projected peak before the next renewal season.",
                "Little headroom remains for seasonal peaks, so a traffic spike degrades quotes, claims or payments directly.",
                20, domain=a["domain"], metrics=dict(utilisation_pct=round(util * 100), peak_tps=a["peak_tps"], capacity_tps=a["capacity_tps"]))
    batch: dict[str, list[dict]] = defaultdict(list)
    for i in s.integrations:
        if i["style"] == "file_batch" and i["target_kind"] == "app":
            batch[i["target_id"]].append(i)
    for tgt, ints in batch.items():
        if len(ints) >= 3:
            add("R-SCALE-002", "scalability", "medium", f"{len(ints)} batch feeds converge on {s.by_id[tgt]['name']}", [tgt] + [i["source_id"] for i in ints],
                [dict(kind="integration", id=i["id"], label=i["name"]) for i in ints], "Replace nightly file drops with streaming ingestion to remove the shared batch window.",
                "Competing batch jobs extend the nightly window and make failure recovery slow.", 30, domain=s.by_id[tgt]["domain"], metrics=dict(feeds=len(ints)))

    # ---- R-SMELL: other design smells
    v1 = next(a for a in s.apis if a.get("special") == "customer_v1")
    add("R-SMELL-001", "smell", "medium", f"Deprecated Customer API v1 is still consumed by {len(v1['consumers'])} applications", v1["consumers"] + [v1["id"]],
        [dict(kind="asset", id=v1["id"], label="Customer API v1")], "Migrate remaining consumers to Customer API v2 and retire v1 on a published date.",
        "Supporting two contract versions doubles testing effort and keeps the legacy customer hub on the critical path.", 40, domain="Customer & Distribution", metrics=dict(consumers=len(v1["consumers"])))
    bypass = [a for a in s.apis if not a["gateway"] and len(a["consumers"]) >= 3 and a["lifecycle"] == "active"]
    if bypass:
        add("R-SMELL-002", "smell", "medium", f"{len(bypass)} widely consumed APIs bypass the API gateway", [a["id"] for a in bypass],
            [dict(kind="asset", id=a["id"], label=f"{a['name']} {a['version']}") for a in bypass[:8]], "Publish each API through Azure API Management with policy-based authentication and rate limits.",
            "Un-gated APIs have no central throttling, analytics or consistent authentication.", len(bypass) * 6, metrics=dict(apis=len(bypass)))
    p2p: dict[str, int] = defaultdict(int)
    for i in s.integrations:
        if i["style"] == "point_to_point" and i["source_kind"] == "app":
            p2p[i["source_id"]] += 1
            p2p[i["target_id"]] += 1
    for aid, n in sorted(p2p.items(), key=lambda kv: -kv[1])[:2]:
        if n >= 4:
            add("R-SMELL-003", "smell", "medium", f"{s.by_id[aid]['name']} has {n} point-to-point integrations", [aid], [dict(kind="asset", id=aid, label=s.by_id[aid]["name"])],
                "Move point-to-point links behind APIs or Kafka topics.", "Each bespoke link adds an interface the team has to monitor, secure and change in lock-step.", n * 10, domain=s.by_id[aid]["domain"], metrics=dict(links=n))
    for dbid, ints in by_db.items():
        db = db_by_id[dbid]
        deps = {u for u, v, d in s.graph.in_edges(dbid, data=True) if d["rel"] in ("uses", "direct_db") and s.graph.nodes[u]["type"] == "application"}
        doms = {s.by_id[x]["domain"] for x in deps}
        if len(doms) >= 4 and dbid == next(d["id"] for d in s.dbs if d["engine"] == "Oracle 12c"):
            claims = [x for x in deps if s.supports(s.by_id[x], "CAP-CLM")]
            add("R-SMELL-004", "smell", "critical", f"{db['name']} (Oracle 12c) is shared by {len(deps)} applications across {len(doms)} domains; {len(claims)} support Claims", sorted(deps) + [dbid],
                [dict(kind="asset", id=x, label=s.by_id[x]["name"]) for x in sorted(deps)],
                "Decouple consumers behind a Policy API and migrate the database to PostgreSQL 15 in wave 2 of the modernization plan.",
                "One out-of-support database underpins Claims, Underwriting, Billing and Distribution. A failure or forced upgrade is a cross-domain incident.",
                240, domain="Policy Admin", metrics=dict(applications=len(deps), claims_applications=len(claims), domains=len(doms)))

    ordered = sorted(raw, key=lambda f: (SEV_ORDER[f["severity"]], CATEGORIES.index(f["category"]), f["title"]))
    for n, f in enumerate(ordered, 1):
        f["id"] = f"F-{n:03d}"
        f["status"] = "open"
        f["detected_at"] = (s.ref_date - timedelta(hours=(n * 7) % 90 + 2)).isoformat()
    return ordered


def summary() -> dict:
    fs = findings()
    by_cat = {c: sum(1 for f in fs if f["category"] == c) for c in CATEGORIES}
    by_sev = {k: sum(1 for f in fs if f["severity"] == k) for k in SEV_ORDER}
    by_dom: dict[str, int] = defaultdict(int)
    for f in fs:
        by_dom[f["domain"]] += 1
    return dict(total=len(fs), by_category=by_cat, by_severity=by_sev, by_domain=dict(by_dom),
                effort_person_days=sum(f["effort"]["person_days"] for f in fs))
