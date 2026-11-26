"""Target-architecture option generator and decision agent. Scores come from NFR-driven functions, text from Jinja2."""

from __future__ import annotations

import re
from datetime import date

from app.mock_ai.narration import render_template
from app.repositories.store import get_store

CRITERIA = ["cost", "security", "scalability", "complexity", "time_to_market"]
CRITERIA_LABEL = {"cost": "Cost efficiency", "security": "Security", "scalability": "Scalability", "complexity": "Simplicity", "time_to_market": "Time to market"}
DEFAULT_WEIGHTS = {"cost": 20, "security": 25, "scalability": 25, "complexity": 15, "time_to_market": 15}

OPTIONS = {
    "A": dict(id="A", key="api-led", name="API-led connectivity", short="API-led", base=dict(cost=7, security=7, scalability=6, complexity=7, time_to_market=8), pattern="PAT-001",
              summary="Layered system, process and experience APIs expose the existing systems of record without changing them."),
    "B": dict(id="B", key="event-driven", name="Event-driven architecture", short="Event-driven", base=dict(cost=6, security=7, scalability=9, complexity=4, time_to_market=5), pattern="PAT-002",
              summary="State changes are published as domain events on Kafka so consumers react asynchronously and evolve independently."),
    "C": dict(id="C", key="cloud-native", name="Cloud-native re-platform", short="Cloud-native", base=dict(cost=4, security=8, scalability=9, complexity=3, time_to_market=3), pattern="PAT-005",
              summary="Rebuild the capability as containerised microservices on AKS with managed data services and full IaC."),
}

PRESETS = {
    "claims-peak": dict(availability=99.95, rto_hours=2, rpo_minutes=5, latency_ms=800, throughput_tps=900, compliance=["GDPR", "SOX"], budget_k=2500, timeline_months=12),
    "quick-win": dict(availability=99.9, rto_hours=4, rpo_minutes=30, latency_ms=500, throughput_tps=150, compliance=["GDPR"], budget_k=600, timeline_months=5),
    "regulated-core": dict(availability=99.99, rto_hours=1, rpo_minutes=1, latency_ms=300, throughput_tps=400, compliance=["GDPR", "SOX", "Solvency II"], budget_k=4000, timeline_months=18),
}


def _clamp(v: float) -> float:
    return max(1.0, min(10.0, round(v, 1)))


def adjusted_scores(nfr: dict) -> dict[str, dict[str, float]]:
    tps = float(nfr.get("throughput_tps", 200))
    lat = float(nfr.get("latency_ms", 800))
    avail = float(nfr.get("availability", 99.9))
    budget = float(nfr.get("budget_k", 1500))
    months = float(nfr.get("timeline_months", 12))
    comp = [c.lower() for c in nfr.get("compliance", [])]
    out = {k: dict(o["base"]) for k, o in OPTIONS.items()}
    if tps >= 800:
        out["A"]["scalability"] -= 1.5; out["B"]["scalability"] += 0.5; out["C"]["scalability"] += 0.5
    elif tps <= 150:
        out["A"]["scalability"] += 1.0
    if lat <= 300:
        out["B"]["scalability"] -= 0.5; out["A"]["complexity"] += 0.3
    if avail >= 99.95:
        out["A"]["scalability"] -= 0.5; out["B"]["scalability"] += 0.5; out["C"]["scalability"] += 0.5
    if months <= 6:
        out["A"]["time_to_market"] += 0.5; out["B"]["time_to_market"] -= 1; out["C"]["time_to_market"] -= 2
    elif months >= 15:
        out["B"]["time_to_market"] += 0.5; out["C"]["time_to_market"] += 1.0
    if budget < 800:
        out["A"]["cost"] += 0.5; out["B"]["cost"] -= 0.5; out["C"]["cost"] -= 1.5
    elif budget >= 3000:
        out["B"]["cost"] += 0.5; out["C"]["cost"] += 1.0
    if any(c in comp for c in ("gdpr", "sox", "solvency ii")):
        out["A"]["security"] += 0.3; out["B"]["security"] += 0.3; out["C"]["security"] += 0.5
    return {k: {c: _clamp(v) for c, v in d.items()} for k, d in out.items()}


def _clean(s: str) -> str:
    return re.sub(r'["\[\]\(\)&]', "", s)


MERMAID = {
    "A": """flowchart LR
  subgraph EXP["Experience APIs"]
    E1["{{ channel }}"]
    E2["Partner / Broker channel"]
  end
  GW["Azure API Management"]
  subgraph PROC["Process APIs (MuleSoft)"]
    P1["{{ domain }} orchestration"]
  end
  subgraph SYS["System APIs"]
{% for s in systems %}
    S{{ loop.index }}["{{ s }} API"]
{% endfor %}
  end
  E1 --> GW
  E2 --> GW
  GW --> P1
{% for s in systems %}
  P1 --> S{{ loop.index }}
  S{{ loop.index }} --> D{{ loop.index }}[("{{ s }} data")]
{% endfor %}""",
    "B": """flowchart LR
  subgraph PRODUCERS["Producers"]
{% for s in systems %}
    S{{ loop.index }}["{{ s }}"]
{% endfor %}
  end
  OB["Transactional outbox / CDC"]
  K[["Kafka: {{ domain }} domain events"]]
  subgraph CONSUMERS["Consumers"]
    C1["{{ channel }}"]
    C2["Customer 360 projection"]
    C3["Analytics (Snowflake)"]
    C4["Notification service"]
  end
{% for s in systems %}
  S{{ loop.index }} --> OB
{% endfor %}
  OB --> K
  K --> C1
  K --> C2
  K --> C3
  K --> C4""",
    "C": """flowchart TB
  FD["Azure Front Door + WAF"] --> APIM["Azure API Management"]
  APIM --> AKS
  subgraph AKS["AKS: {{ domain }} microservices"]
{% for s in systems %}
    M{{ loop.index }}["{{ s }} service"]
{% endfor %}
  end
  AKS --> PG[("PostgreSQL 15 flexible server")]
  AKS --> KV["Key Vault (private endpoint)"]
  AKS --> EH[["Kafka / Event Hubs"]]
  AKS -. managed identity .-> MON["Monitor + Sentinel"]""",
}

COMPONENTS = {
    "A": [("Azure API Management", "Edge gateway, throttling, authentication", "Azure API Management"), ("Process API layer", "Orchestrates multi-system journeys", "MuleSoft Anypoint"),
          ("System APIs", "Stable contracts in front of each system of record", "MuleSoft / Spring Boot 3"), ("Developer portal", "Discovery, subscriptions and contract testing", "APIM portal")],
    "B": [("Kafka event backbone", "Durable, replayable domain events", "Apache Kafka (Confluent)"), ("Transactional outbox / CDC", "Atomic publication of state changes", "Debezium"),
          ("Schema registry", "Versioned event contracts", "Confluent Schema Registry"), ("Read-model projections", "Query-optimised views fed by events", "Cosmos DB / PostgreSQL 15")],
    "C": [("AKS landing zone", "Containerised services with private networking", "AKS 1.29"), ("Managed data tier", "Zone-redundant PostgreSQL with PITR", "PostgreSQL 15 Flexible Server"),
          ("Platform services", "Key Vault, Monitor and Defender via private endpoints", "Azure PaaS"), ("Infrastructure as code", "Repeatable environments and policy as code", "Terraform")],
}

TRADEOFFS = {
    "A": dict(pros=["Fastest route to value: existing systems are wrapped, not replaced", "Central security, throttling and analytics at the gateway", "Aligned with approved pattern STD-PAT-001"],
              cons=["Synchronous chains inherit the availability of the weakest system", "Does not remove the underlying legacy platforms", "Throughput limited by systems of record"]),
    "B": dict(pros=["Producers and consumers scale and fail independently", "Buffers peaks and enables replay after incidents", "Removes direct database coupling in favour of events"],
              cons=["Eventual consistency must be designed into the user journeys", "Needs event governance, schema discipline and new skills", "Harder end-to-end debugging"]),
    "C": dict(pros=["Elastic scaling and zone resilience by default", "Retires unsupported runtimes and databases in one move", "Everything is code, policy-checked and repeatable"],
              cons=["Highest cost and longest delivery time", "Large data-migration and regression-test effort", "Concentrated delivery risk without a strangler approach"]),
}


def _domain_systems(domain: str) -> tuple[list[str], str]:
    s = get_store()
    apps = [a for a in s.apps if a["domain"] == domain and a["kind"] != "saas"]
    apps.sort(key=lambda a: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[a["criticality"]], a["name"]))
    names = [_clean(a["name"]) for a in apps[:3]] or ["Core system"]
    chan = next((a["name"] for a in s.apps if a["domain"] == domain and a["internet_facing"]), "Digital channel")
    return names, _clean(chan)


def generate_options(goals: str, domain: str, nfr: dict) -> dict:
    scores = adjusted_scores(nfr)
    systems, channel = _domain_systems(domain)
    s = get_store()
    legacy = sum(1 for a in s.apps if a["domain"] == domain and a["lifecycle"] != "supported")
    options = []
    for oid, o in OPTIONS.items():
        sc = scores[oid]
        fit = round(sum(sc[c] * DEFAULT_WEIGHTS[c] for c in CRITERIA) / sum(DEFAULT_WEIGHTS.values()) * 10 + (4 if oid == "A" and legacy >= 2 else 0) + (3 if oid == "C" and legacy >= 3 else 0))
        scale = 1 + len(systems) * 0.25
        dur = {"A": 5, "B": 8, "C": 14}[oid]
        cost = {"A": 650, "B": 1100, "C": 2300}[oid]
        diagram = render_template(MERMAID[oid], domain=_clean(domain), channel=channel, systems=systems)
        options.append(dict(
            id=oid, key=o["key"], name=o["name"], short=o["short"], summary=o["summary"], fit_score=min(97, fit), scores=sc, diagram=diagram,
            components=[dict(name=n, role=r, technology=t) for n, r, t in COMPONENTS[oid]], pros=TRADEOFFS[oid]["pros"], cons=TRADEOFFS[oid]["cons"],
            estimated_cost_k=round(cost * scale / 50) * 50, estimated_months=round(dur * (0.9 + len(systems) * 0.1)), pattern_id=o["pattern"],
        ))
    options.sort(key=lambda o: -o["fit_score"])
    return dict(domain=domain, goals=goals, nfr=nfr, options=options, systems=systems)


# ------------------------------------------------------------------ decision agent
REASONS = {
    ("B", "scalability"): "Kafka buffers peaks, so the {tps} tps requirement is met without sizing every system of record for burst load.",
    ("B", "security"): "Events replace direct database reads, removing cross-domain table access flagged by STD-SEC-015.",
    ("B", "cost"): "Consumers are added without changing producers, so each new integration costs less than a point-to-point build.",
    ("B", "complexity"): "Event governance adds operational overhead, which is the main cost of this option.",
    ("B", "time_to_market"): "Delivery is incremental: topics and consumers can ship domain by domain.",
    ("A", "time_to_market"): "Existing systems are wrapped rather than replaced, so the first APIs can ship within weeks.",
    ("A", "cost"): "Re-use of current platforms keeps spend within the {budget}k budget envelope.",
    ("A", "complexity"): "The pattern is already established in the estate (MuleSoft and API Management), so the learning curve is small.",
    ("A", "security"): "Authentication, throttling and audit are enforced centrally at the gateway.",
    ("A", "scalability"): "Adequate for the stated load, but synchronous calls remain bound by the capacity of the systems behind them.",
    ("C", "scalability"): "Elastic scaling and zone redundancy meet the {avail}% availability target by default.",
    ("C", "security"): "Private endpoints, managed identity and policy-as-code are the baseline rather than retrofits.",
    ("C", "cost"): "Highest upfront cost; savings come only after legacy run costs are retired.",
    ("C", "complexity"): "Re-platforming multiplies migration and regression-test effort.",
    ("C", "time_to_market"): "Full re-platforming is the slowest route to production value.",
}
EVIDENCE = {
    "A": [("standard", "STD-PAT-001", "API-led connectivity for synchronous integration"), ("adr", "ADR-0040", "MuleSoft for system and process APIs")],
    "B": [("standard", "STD-PAT-002", "Event-driven architecture for cross-domain propagation"), ("adr", "ADR-0031", "Adopt Kafka as the enterprise event backbone"), ("finding", "F-001", "Direct DB integrations should move behind APIs/events")],
    "C": [("standard", "STD-PAT-003", "Strangler-fig for legacy replacement"), ("standard", "STD-CLD-002", "Infrastructure provisioned as code")],
}


def evaluate(nfr: dict, weights: dict | None = None, options: list[dict] | None = None) -> dict:
    w = dict(DEFAULT_WEIGHTS, **(weights or {}))
    total_w = sum(w.values()) or 1
    scores = adjusted_scores(nfr)
    opts = options or [dict(id=k, name=o["name"], short=o["short"]) for k, o in OPTIONS.items()]

    def rank(wts: dict[str, float]) -> list[tuple[str, float]]:
        tw = sum(wts.values()) or 1
        return sorted(((o["id"], round(sum(scores[o["id"]][c] * wts[c] for c in CRITERIA) / tw, 2)) for o in opts), key=lambda x: -x[1])

    ranked = rank(w)
    winner = ranked[0][0]
    runner = ranked[1][0]
    matrix = [dict(option=o["id"], name=o["name"], scores=scores[o["id"]], weighted=dict(ranked).get(o["id"], 0)) for o in opts]
    for m in matrix:
        m["rank"] = [r[0] for r in ranked].index(m["option"]) + 1
        m["contribution"] = {c: round(scores[m["option"]][c] * w[c] / total_w, 2) for c in CRITERIA}
    # sensitivity: swing each weight by -50%/+50% and see whether the winner changes
    sens = []
    for c in CRITERIA:
        flips = []
        for factor in (0.5, 1.5):
            alt = dict(w)
            alt[c] = w[c] * factor
            top = rank(alt)[0][0]
            flips.append(dict(factor=factor, winner=top, changed=top != winner))
        sens.append(dict(criterion=c, label=CRITERIA_LABEL[c], flips=flips, robust=not any(f["changed"] for f in flips)))
    # reasons: criteria where the winner leads the runner-up most
    lead = sorted(CRITERIA, key=lambda c: -(scores[winner][c] - scores[runner][c]) * w[c])
    chosen = [c for c in lead if scores[winner][c] >= scores[runner][c]][:4] or lead[:3]
    ctx = dict(tps=nfr.get("throughput_tps", 200), budget=nfr.get("budget_k", 1500), avail=nfr.get("availability", 99.9))
    reasons = [REASONS[(winner, c)].format(**ctx) for c in chosen if (winner, c) in REASONS][:5]
    if len(reasons) < 3:
        reasons += [REASONS[(winner, c)].format(**ctx) for c in CRITERIA if (winner, c) in REASONS and REASONS[(winner, c)].format(**ctx) not in reasons][: 3 - len(reasons)]
    win_name = next(o["name"] for o in opts if o["id"] == winner)
    margin = round(ranked[0][1] - ranked[1][1], 2)
    robustness = sum(1 for x in sens if x["robust"]) / len(sens)
    confidence = round(min(0.97, 0.62 + margin * 0.12 + robustness * 0.18), 2)
    radar = [dict(option=o["id"], name=o["name"], values=[scores[o["id"]][c] for c in CRITERIA]) for o in opts]
    return dict(weights=w, criteria=[dict(key=c, label=CRITERIA_LABEL[c]) for c in CRITERIA], matrix=matrix, ranking=[dict(option=i, score=sc) for i, sc in ranked], radar=radar,
                recommendation=dict(option=winner, name=win_name, headline=f"Recommend {win_name.lower() if winner != 'A' else 'API-led connectivity'} because", reasons=reasons, margin=margin, runner_up=runner),
                sensitivity=sens, evidence=[dict(kind=k, id=i, label=l) for k, i, l in EVIDENCE[winner]], confidence=confidence)


# --------------------------------------------------------------------- ADR
ADR_TEMPLATE = """# {{ number }}: {{ title }}

- **Status:** {{ status }}
- **Date:** {{ date }}
- **Deciders:** {{ deciders | commas }}
- **Domain:** {{ domain }}

## Context

{{ context }}

Key drivers: {{ drivers | commas }}.

## Decision

We will adopt **{{ chosen }}**.

{% for r in reasons %}
- {{ r }}
{% endfor %}

## Options considered

| Option | Weighted score | Notes |
|---|---|---|
{% for o in options %}
| {{ o.name }} | {{ o.score }} | {{ o.note }} |
{% endfor %}

## Consequences

- Teams will plan delivery against the {{ chosen }} reference blueprint.
- Exceptions to this decision require design-authority approval.
- This ADR is reviewed after {{ review_months }} months or when the drivers change.

## Evidence

{% for e in evidence %}
- `{{ e.id }}`: {{ e.label }}
{% endfor %}
"""


def next_adr_number() -> str:
    s = get_store()
    nums = [int(d["adr"]["number"].split("-")[1]) for d in s.documents if d.get("adr")]
    return f"ADR-{max(nums + [48]) + 1 + len(_new_adrs):04d}"


_new_adrs: list[dict] = []


def make_adr(title: str, domain: str, nfr: dict, weights: dict | None, chosen_option: str | None = None, context: str | None = None) -> dict:
    ev = evaluate(nfr, weights)
    cid = chosen_option or ev["recommendation"]["option"]
    chosen = OPTIONS[cid]["name"]
    options = [dict(name=m["name"], score=next(r["score"] for r in ev["ranking"] if r["option"] == m["option"]), note=OPTIONS[m["option"]]["summary"]) for m in ev["matrix"]]
    number = next_adr_number()
    md = render_template(
        ADR_TEMPLATE, number=number, title=title, status="Proposed", date=date.today().isoformat(), deciders=["Architecture Review Board", "Avadhi Jain (Chief Architect)"], domain=domain,
        context=context or f"The {domain} domain needs a target architecture that satisfies availability of {nfr.get('availability', 99.9)}%, RTO of {nfr.get('rto_hours', 4)}h and a throughput of {nfr.get('throughput_tps', 200)} tps within a budget of {nfr.get('budget_k', 1500)}k.",
        drivers=[CRITERIA_LABEL[c] for c in sorted(CRITERIA, key=lambda c: -ev["weights"][c])[:3]], chosen=chosen, reasons=ev["recommendation"]["reasons"], options=options, review_months=12, evidence=ev["evidence"],
    )
    rec = dict(number=number, title=title, status="proposed", domain=domain, date=date.today().isoformat(), decision=f"Adopt {chosen}.", source="generated")
    _new_adrs.append(rec)
    return dict(number=number, title=title, markdown=md, filename=f"{number.lower()}-{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}.md", recommendation=ev["recommendation"], confidence=ev["confidence"], evidence=ev["evidence"])


def decision_log() -> list[dict]:
    s = get_store()
    seeded = [dict(number=d["adr"]["number"], title=d["title"].split(": ", 1)[1], status=d["adr"]["status"], domain=d["domain"], date=d["adr"]["date"], decision=d["adr"]["decision"], source="repository", document_id=d["id"])
              for d in s.documents if d.get("adr")]
    return sorted(_new_adrs + seeded, key=lambda r: r["number"], reverse=True)
