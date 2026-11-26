"""Modernization planner: converts current-to-target gaps into three waves with a dependency-aware schedule."""

from __future__ import annotations

from functools import lru_cache

from app.mock_ai.rules import assessment
from app.repositories.store import get_store

WAVES = [
    dict(id="W1", name="Wave 1: APIs", theme="Put stable APIs in front of systems of record and stop direct database access.", color="accent"),
    dict(id="W2", name="Wave 2: Data decoupling", theme="Decouple and retire legacy data platforms; consolidate duplicated systems of record.", color="low"),
    dict(id="W3", name="Wave 3: Agentification", theme="Build guard-railed AI agents on top of the new APIs and events.", color="healthy"),
]
BASE_PD = {"legacy": 90, "package": 70, "custom": 45, "microservice": 20, "platform": 55, "saas": 15}
SCENARIOS = {
    "aggressive": dict(label="Aggressive", duration=0.72, cost=1.22, risk_shift=1, parallel=True, blurb="Run waves in parallel with a larger team. Fastest value, highest delivery risk."),
    "balanced": dict(label="Balanced", duration=1.0, cost=1.0, risk_shift=0, parallel=True, blurb="Overlap waves where dependencies allow. Recommended."),
    "conservative": dict(label="Conservative", duration=1.3, cost=0.94, risk_shift=-1, parallel=False, blurb="Finish each wave before starting the next. Lowest risk, slowest value."),
}
RISK = ["low", "medium", "high", "critical"]


def _risk(level: str, shift: int) -> str:
    return RISK[max(0, min(3, RISK.index(level) + shift))]


@lru_cache
def _items() -> list[dict]:
    s = get_store()
    A = s.app_by_key
    if "GWCC" not in A:
        db2 = s.dbs[0]
        db_deps = sorted({u for u, v, d in s.graph.in_edges(db2["id"], data=True) if d["rel"] in ("uses", "direct_db")})
        direct_sources = sorted({i["source_id"] for i in s.integrations if i["style"] == "direct_db" and i["source_kind"] == "app"})
        rows = [
            ("W1-1", "W1", "Strangler API & Event facade in front of Claims Core", ["APP-001", "APP-002"], 95, "high", 520, 10, [], "Expose governed REST APIs and domain events via Claims API Gateway in front of Claims Core."),
            ("W1-2", "W1", "Move Regulatory Reporting & Batch Processor off direct Claims Db2 reads", direct_sources, 80, "high", 410, 12, ["W1-1"], f"Replace {len(direct_sources)} direct IBM Db2 queries with Claims API and event subscriptions."),
            ("W1-3", "W1", "Remediate Azure storage & PostgreSQL private endpoint drift", ["APP-004"], 35, "medium", 240, 6, [], "Disable public network access and enforce TLS 1.2 on Customer Service Portal Azure resources."),
            ("W2-1", "W2", "Break 3-system batch cycle (Claims Core, Payment Service, Finance Recon)", ["APP-001", "APP-003", "APP-008"], 110, "high", 480, 14, ["W1-1"], "Replace bidirectional SFTP and nightly batch adjustments with asynchronous settlement events."),
            ("W2-2", "W2", "Migrate Claims Db2 to Azure Database for PostgreSQL (Multi-AZ)", [db2["id"]] + db_deps, 150, "critical", 680, 18, ["W1-2", "W2-1"], "Establish warm DR standby, cut over with CDC, and decommission single-instance on-prem Claims Db2."),
            ("W2-3", "W2", "Retire WebSphere 8.5 and Finance Reconciliation legacy stack", ["APP-001", "APP-006", "APP-008"], 120, "medium", 590, 16, ["W2-1"], "Decommission end-of-life WebSphere 8.5 runtimes and sunset Finance Reconciliation."),
            ("W3-1", "W3", "Launch Azure Claims Notification & Fraud Scoring event services", ["APP-002", "APP-004"], 65, "medium", 460, 10, ["W1-1", "W2-1"], "Deploy cloud-native Claims Notification Service and real-time Fraud Scorer on Azure."),
            ("W3-2", "W3", "Guard-railed Claims Triage & Settlement AI Copilot", ["APP-001", "APP-002", "APP-004"], 75, "low", 540, 10, ["W2-2", "W3-1"], "AI agent assisting claims handlers over governed Claims APIs with human-in-the-loop settlement approval."),
        ]
        items = []
        for iid, wave, name, assets, effort, risk, val, weeks, deps, desc in rows:
            items.append(dict(id=iid, wave=wave, name=name, description=desc, asset_ids=assets, asset_count=len(assets), effort_pd=effort, cost_k=round(effort * 0.65), risk=risk, value_k=val, duration_weeks=weeks, depends_on=deps))
        return items
    oracle = next(d for d in s.dbs if d["engine"] == "Oracle 12c")
    ora_deps = sorted({u for u, v, d in s.graph.in_edges(oracle["id"], data=True) if d["rel"] in ("uses", "direct_db")})
    v1 = next(a for a in s.apis if a.get("special") == "customer_v1")
    direct = [i for i in s.integrations if i["style"] == "direct_db"]
    direct_sources = sorted({i["source_id"] for i in direct if i["source_kind"] == "app" and i["target_id"] != oracle["id"]})
    cust_masters = [a["id"] for a in s.apps if a.get("role") == "customer_master"]
    old_stack = [a["id"] for a in s.apps if {"SQL Server 2014", "Windows Server 2012"} & set(a["tech"])]
    bypass = [a["id"] for a in s.apis if not a["gateway"] and len(a["consumers"]) >= 3 and a["lifecycle"] == "active"]

    def pd(ids: list[str], factor: float = 1.0) -> int:
        return round(sum(BASE_PD[s.by_id[i]["kind"]] for i in ids if s.by_id[i]["_type"] == "application") * factor) or 20

    def value(ids: list[str], factor: float = 0.28) -> int:
        return round(sum(s.by_id[i]["annual_cost_k"] for i in ids if s.by_id[i]["_type"] == "application") * factor)

    rows = [
        # id, wave, name, assets, effort, risk, value, weeks, deps, description
        ("W1-1", "W1", "Publish Customer API v2 and retire v1", v1["consumers"], pd(v1["consumers"], 0.35), "medium", value(v1["consumers"], 0.1), 8, [], "Migrate the remaining v1 consumers and switch off the deprecated contract."),
        ("W1-2", "W1", "Policy API facade over Policy Master DB", ora_deps, pd(ora_deps, 0.45), "high", value(ora_deps, 0.12), 12, [], f"Expose Policy Master DB through a system API so {len(ora_deps)} Oracle 12c dependents stop reading tables directly."),
        ("W1-3", "W1", "Claims mainframe API facade (strangler-fig)", [A["CMF"]["id"], A["CPH"]["id"], A["GWCC"]["id"]], 160, "high", value([A["CMF"]["id"]], 0.2), 14, [], "REST facade in front of Claims Mainframe Core with routing for migrated capabilities."),
        ("W1-4", "W1", "Replace remaining direct DB integrations", direct_sources, pd(direct_sources, 0.5), "medium", value(direct_sources, 0.06), 10, ["W1-2"], f"Move {len(direct_sources)} further direct database integrations behind APIs or events."),
        ("W1-5", "W1", "Bring ungated APIs behind API Management", bypass, max(25, len(bypass) * 6), "low", 120, 6, [], f"Publish {len(bypass)} widely consumed APIs through the gateway."),
        ("W2-1", "W2", "Migrate Policy Master DB to PostgreSQL 15", [oracle["id"]] + ora_deps, pd(ora_deps, 0.9), "critical", value(ora_deps, 0.22), 20, ["W1-2", "W1-4"], "Retire Oracle 12c after consumers are decoupled; cut over with CDC and a rollback window."),
        ("W2-2", "W2", "Consolidate three customer masters onto MDM", cust_masters, pd(cust_masters, 1.1), "high", value(cust_masters, 0.3), 24, ["W1-1"], "Single system of record for customer data; Salesforce and the legacy hub become consumers."),
        ("W2-3", "W2", "Event backbone for policy and claim events", [A["KAFKA"]["id"], A["PAC"]["id"], A["GWCC"]["id"]], 120, "medium", 260, 12, ["W1-2"], "Outbox and CDC publish domain events so downstream systems stop polling."),
        ("W2-4", "W2", "Retire SQL Server 2014 and Windows Server 2012", old_stack, pd(old_stack, 0.6), "medium", value(old_stack, 0.35), 18, ["W1-4"], f"Re-platform or retire {len(old_stack)} applications on unsupported infrastructure."),
        ("W2-5", "W2", "Retire Teradata into Snowflake", [A["EDW"]["id"], A["SNOW"]["id"]], 140, "medium", value([A["EDW"]["id"]], 0.7), 16, ["W2-3"], "Move remaining workloads and decommission the Teradata appliance."),
        ("W3-1", "W3", "Claims Copilot to a guard-railed claims agent", [A["CCOP"]["id"], A["AIGW"]["id"]], 90, "high", 450, 12, ["W1-3", "W2-3"], "Agent with read tools over the claims API and human approval for any settlement action."),
        ("W3-2", "W3", "Underwriting assistant agent", [A["UWB"]["id"], A["RSS"]["id"]], 70, "medium", 380, 10, ["W1-2"], "Drafts referrals and risk summaries from policy and third-party data."),
        ("W3-3", "W3", "Customer service agent", [A["CSP"]["id"], A["CNH"]["id"], A["CPM"]["id"]], 80, "medium", 520, 10, ["W2-2"], "Handles routine servicing journeys over the Customer API v2 and consent service."),
        ("W3-4", "W3", "AI gateway and agent tool registry", [A["AIGW"]["id"], A["AOAI"]["id"]], 55, "low", 150, 8, ["W1-5"], "Central policy, audit and tool catalogue for all agents."),
    ]
    items = []
    for iid, wave, name, assets, effort, risk, val, weeks, deps, desc in rows:
        items.append(dict(id=iid, wave=wave, name=name, description=desc, asset_ids=assets, asset_count=len(assets), effort_pd=effort, cost_k=round(effort * 0.65), risk=risk, value_k=val, duration_weeks=weeks, depends_on=deps))
    return items


def _addressed_findings() -> dict[str, list[str]]:
    fs = assessment.findings()
    m = {"W1-2": ["R-DB-001", "R-SMELL-004"], "W1-4": ["R-DB-002"], "W2-1": ["R-OBS-001"], "W2-2": ["R-DUP-001"], "W2-4": ["R-UNS-001"], "W1-3": ["R-SPOF-001"], "W1-1": ["R-SMELL-001"]}
    return {k: [f["id"] for f in fs if f["rule_id"] in v][:6] for k, v in m.items()}


def scenarios() -> list[dict]:
    return [dict(id=k, **{x: v for x, v in d.items() if x in ("label", "blurb", "duration", "cost", "risk_shift", "parallel")}) for k, d in SCENARIOS.items()]


def plan(scenario: str = "balanced", overrides: dict[str, int] | None = None) -> dict:
    sc = SCENARIOS[scenario]
    addressed = _addressed_findings()
    items = [dict(i) for i in _items()]
    by_id = {i["id"]: i for i in items}
    wave_start = {"W1": 0, "W2": 8 if sc["parallel"] else None, "W3": 18 if sc["parallel"] else None}
    for i in items:
        i["duration_weeks"] = max(3, round(i["duration_weeks"] * sc["duration"]))
        i["cost_k"] = round(i["cost_k"] * sc["cost"])
        i["risk"] = _risk(i["risk"], sc["risk_shift"])
        i["findings"] = addressed.get(i["id"], [])
    order: list[dict] = []
    seen: set[str] = set()

    def visit(i: dict) -> None:
        if i["id"] in seen:
            return
        seen.add(i["id"])
        for d in i["depends_on"]:
            visit(by_id[d])
        order.append(i)

    for i in items:
        visit(i)
    overrides = overrides or {}
    adjusted: list[str] = []
    wave_end = {"W1": 0, "W2": 0, "W3": 0}
    for i in order:
        dep_end = max((by_id[d]["end_week"] for d in i["depends_on"]), default=0)
        base = wave_start.get(i["wave"])
        if base is None:  # conservative: a wave starts only after the previous one finishes
            prev = {"W2": "W1", "W3": "W2"}[i["wave"]]
            base = wave_end[prev]
        start = max(dep_end, base)
        if i["id"] in overrides:
            wanted = max(0, int(overrides[i["id"]]))
            if wanted < dep_end:
                adjusted.append(i["id"])
            start = max(wanted, dep_end)
        i["start_week"] = start
        i["end_week"] = start + i["duration_weeks"]
        wave_end[i["wave"]] = max(wave_end[i["wave"]], i["end_week"])
    # critical path: longest dependency chain by end_week
    last = max(items, key=lambda x: x["end_week"])
    cp, cur = [], last
    while cur:
        cp.append(cur["id"])
        cur = max((by_id[d] for d in cur["depends_on"]), key=lambda x: x["end_week"], default=None)
    for i in items:
        i["critical"] = i["id"] in cp
        i["status"] = "planned"
    waves = []
    for w in WAVES:
        ws = [i for i in items if i["wave"] == w["id"]]
        waves.append(dict(w, items=[i["id"] for i in ws], start_week=min(i["start_week"] for i in ws), end_week=max(i["end_week"] for i in ws), cost_k=sum(i["cost_k"] for i in ws),
                          value_k=sum(i["value_k"] for i in ws), effort_pd=sum(i["effort_pd"] for i in ws), asset_count=len({a for i in ws for a in i["asset_ids"]}),
                          risk=max((i["risk"] for i in ws), key=RISK.index)))
    horizon = max(i["end_week"] for i in items)
    months = int(horizon / 4.345) + 6
    curve = []
    for m in range(0, months + 1, 1):
        wk = m * 4.345
        cost = sum(i["cost_k"] * min(1, max(0, (wk - i["start_week"]) / i["duration_weeks"])) for i in items)
        val = sum(i["value_k"] / 12 * max(0, (wk - i["end_week"]) / 4.345) for i in items)
        curve.append(dict(month=m, cumulative_cost_k=round(cost), cumulative_value_k=round(val)))
    milestones = [dict(id=f"M-{w['id']}", name=f"{w['name'].split(':')[0]} complete", week=w["end_week"], wave=w["id"]) for w in waves]
    be = next((c["month"] for c in curve if c["cumulative_value_k"] >= c["cumulative_cost_k"] and c["month"] > 0), None)
    return dict(scenario=scenario, scenario_label=sc["label"], blurb=sc["blurb"], waves=waves, items=sorted(items, key=lambda i: (i["wave"], i["start_week"])), milestones=milestones, critical_path=cp[::-1],
                adjusted=adjusted, totals=dict(duration_weeks=horizon, cost_k=sum(i["cost_k"] for i in items), value_k=sum(i["value_k"] for i in items), effort_pd=sum(i["effort_pd"] for i in items),
                                               assets=len({a for i in items for a in i["asset_ids"]}), break_even_month=be), value_curve=curve)
