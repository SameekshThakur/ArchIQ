"""Technical-debt scoring. Every score is derived from asset attributes and graph metrics (0-100, higher = more debt)."""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from functools import lru_cache

from app.mock_ai.graph import analysis as A
from app.repositories.store import get_store

DIMENSIONS = ["legacy", "security", "resilience", "cost", "maintainability"]
WEIGHTS = {"legacy": 0.25, "security": 0.25, "resilience": 0.20, "cost": 0.10, "maintainability": 0.20}
CRIT_W = {"critical": 4, "high": 3, "medium": 2, "low": 1}
EFFORT_BASE = {"legacy": 600, "package": 380, "custom": 300, "microservice": 80, "platform": 220, "saas": 40}
DR_PENALTY = {"none": 28, "cold": 18, "warm": 6, "hot": 0}


def _cap(x: float) -> int:
    return int(max(0, min(100, round(x))))


@lru_cache
def drifted_resources_by_app() -> dict[str, int]:
    s = get_store()
    out: dict[str, int] = {}
    for r in s.cloud:
        if r.get("drift_meta") and r["app_id"]:
            out[r["app_id"]] = out.get(r["app_id"], 0) + 1
    return out


@lru_cache
def public_resources_by_app() -> dict[str, int]:
    s = get_store()
    out: dict[str, int] = {}
    for r in s.cloud:
        if r["app_id"] and r["deployed"].get("public_network_access") is True:
            out[r["app_id"]] = out.get(r["app_id"], 0) + 1
    return out


@lru_cache
def app_scores() -> dict[str, dict]:
    s = get_store()
    cp = A.coupling()
    spof_ids = {x["app_id"] for x in A.spofs()}
    cluster_ids = {a for c in cp["clusters"] for a in c}
    roles: dict[str, int] = {}
    for a in s.apps:
        if a.get("role"):
            roles[a["role"]] = roles.get(a["role"], 0) + 1
    direct_by_app: dict[str, int] = {}
    for i in s.integrations:
        if i["style"] == "direct_db" and i["source_kind"] == "app":
            direct_by_app[i["source_id"]] = direct_by_app.get(i["source_id"], 0) + 1
    drift = drifted_resources_by_app()
    public = public_resources_by_app()
    out: dict[str, dict] = {}
    for a in s.apps:
        why: dict[str, list[str]] = {d: [] for d in DIMENSIONS}
        # legacy
        eol_tech = [t for t in a["tech"] if s.technologies.get(t, {}).get("lifecycle") == "eol"]
        legacy = {"supported": 12, "extended": 50, "eol": 82}[a["lifecycle"]] + min(18, a["age_years"] * 0.7) + min(18, len(eol_tech) * 6)
        if a["hosting"] in ("mainframe",) or "AS/400 RPG" in a["tech"]:
            legacy += 6
        if eol_tech:
            why["legacy"].append("End-of-life technology: " + ", ".join(eol_tech))
        if a["lifecycle"] != "supported":
            why["legacy"].append(f"Application lifecycle is {a['lifecycle']}")
        # security
        sec = a["vulns_critical"] * 13 + a["vulns_high"] * 2.5 + (15 if a["internet_facing"] and a["lifecycle"] == "eol" else 0)
        sec += public.get(a["id"], 0) * 9 + drift.get(a["id"], 0) * 8 + direct_by_app.get(a["id"], 0) * 4
        if a["vulns_critical"]:
            why["security"].append(f"{a['vulns_critical']} critical and {a['vulns_high']} high open vulnerabilities")
        if public.get(a["id"]):
            why["security"].append(f"{public[a['id']]} cloud resource(s) with public network access")
        if drift.get(a["id"]):
            why["security"].append(f"{drift[a['id']]} drifted resource(s) from the approved design")
        if direct_by_app.get(a["id"]):
            why["security"].append(f"{direct_by_app[a['id']]} direct database integration(s)")
        # resilience
        res = (24 if a["single_instance"] else 0) + DR_PENALTY[a["dr_tier"]] + (22 if a["id"] in spof_ids else 0) + min(15, cp["degree"].get(a["id"], 0) * 0.5)
        if a["single_instance"]:
            why["resilience"].append("Single instance deployment")
        if a["dr_tier"] in ("none", "cold"):
            why["resilience"].append(f"DR tier '{a['dr_tier']}' for a {a['criticality']} system")
        if a["id"] in spof_ids:
            why["resilience"].append("Identified as a single point of failure")
        # cost
        cost = 20 + {"supported": 0, "extended": 15, "eol": 25}[a["lifecycle"]] + (20 if a.get("role") and roles[a["role"]] > 1 else 0)
        cost += 10 if a["annual_cost_k"] > 2000 else 0
        cost += 15 if (a["users"] and a["users"] < 200 and a["annual_cost_k"] > 800) else 0
        if a.get("role") and roles[a["role"]] > 1:
            why["cost"].append(f"Duplicated capability: {roles[a['role']]} systems share the '{a['role'].replace('_', ' ')}' role")
        if a["lifecycle"] != "supported":
            why["cost"].append("Extended-support premium on licences")
        # maintainability
        mnt = (100 - a["test_coverage"]) * 0.45 + min(25, a["loc_k"] / 50) + (100 - a["doc_coverage"]) * 0.2 + cp["betweenness"].get(a["id"], 0) * 60 + (12 if a["id"] in cluster_ids else 0)
        if a["test_coverage"] < 40:
            why["maintainability"].append(f"Test coverage only {a['test_coverage']}%")
        if a["id"] in cluster_ids:
            why["maintainability"].append("Part of a tightly coupled dependency cycle")
        if a["doc_coverage"] < 45:
            why["maintainability"].append(f"Documentation coverage {a['doc_coverage']}%")
        scores = {"legacy": _cap(legacy), "security": _cap(sec), "resilience": _cap(res), "cost": _cap(cost), "maintainability": _cap(mnt)}
        overall = _cap(sum(scores[d] * WEIGHTS[d] for d in DIMENSIONS))
        effort = round(overall / 100 * EFFORT_BASE[a["kind"]] * (1 + a["loc_k"] / 800))
        out[a["id"]] = dict(app_id=a["id"], name=a["name"], domain=a["domain"], criticality=a["criticality"], scores=scores, overall=overall,
                            why=why, effort_pd=effort, remediation_cost_k=round(effort * 0.65, 1))
    return out


def domain_heatmap() -> dict:
    s = get_store()
    scores = app_scores()
    domains = [d for d in sorted({a["domain"] for a in s.apps})]
    cells, totals = [], {}
    for d in domains:
        rows = [scores[a["id"]] for a in s.apps if a["domain"] == d]
        w = [CRIT_W[r["criticality"]] for r in rows]
        for dim in DIMENSIONS:
            v = sum(r["scores"][dim] * wt for r, wt in zip(rows, w)) / sum(w)
            cells.append(dict(domain=d, dimension=dim, score=round(v), apps=len(rows)))
        totals[d] = round(sum(r["overall"] * wt for r, wt in zip(rows, w)) / sum(w))
    return dict(domains=domains, dimensions=DIMENSIONS, cells=cells, domain_overall=totals, weights=WEIGHTS)


def contributors(domain: str | None = None, dimension: str | None = None, limit: int = 15) -> list[dict]:
    rows = [r for r in app_scores().values() if not domain or r["domain"] == domain]
    key = (lambda r: r["scores"][dimension] * CRIT_W[r["criticality"]]) if dimension else (lambda r: r["overall"] * CRIT_W[r["criticality"]])
    out = []
    for r in sorted(rows, key=key, reverse=True)[:limit]:
        out.append(dict(r, dimension_score=r["scores"][dimension] if dimension else r["overall"], drivers=r["why"][dimension] if dimension else
                        [x for d in DIMENSIONS for x in r["why"][d]][:3]))
    return out


def trends(domain: str | None = None) -> dict:
    """12-month trend per dimension ending at today's computed value (deterministic back-cast)."""
    s = get_store()
    hm = domain_heatmap()
    cur = {d: [c for c in hm["cells"] if (domain is None or c["domain"] == domain) and c["dimension"] == d] for d in DIMENSIONS}
    series = {}
    months = [(s.ref_date - timedelta(days=30 * (11 - i))).strftime("%b %y") for i in range(12)]
    for dim in DIMENSIONS:
        now = round(sum(c["score"] for c in cur[dim]) / len(cur[dim]))
        seed = int(hashlib.sha1(f"{domain}:{dim}".encode()).hexdigest()[:8], 16)
        r = random.Random(seed)
        slope = {"legacy": 0.9, "security": -0.6, "resilience": -0.3, "cost": 0.4, "maintainability": 0.2}[dim] + r.uniform(-0.4, 0.4)
        pts = [max(0, min(100, now - slope * (11 - i) + r.uniform(-1.6, 1.6))) for i in range(12)]
        pts[-1] = now
        series[dim] = [round(p, 1) for p in pts]
    overall = [round(sum(series[d][i] * WEIGHTS[d] for d in DIMENSIONS), 1) for i in range(12)]
    return dict(months=months, series=series, overall=overall, domain=domain)


def estate_overall() -> int:
    s = get_store()
    sc = app_scores()
    w = [CRIT_W[a["criticality"]] for a in s.apps]
    return round(sum(sc[a["id"]]["overall"] * x for a, x in zip(s.apps, w)) / sum(w))
