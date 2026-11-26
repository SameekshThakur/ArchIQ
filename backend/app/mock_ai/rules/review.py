"""Automated architecture review: standards + NFR coverage + estate risk + pattern alignment -> readiness score."""

from __future__ import annotations

from app.mock_ai.rules import assessment, standards
from app.repositories import persist
from app.repositories.store import get_store

SEV_PEN = {"critical": 16, "high": 8, "medium": 4, "low": 1.5}
SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
REQUIRED_NFR = ["availability", "rto_hours", "rpo_minutes", "latency_ms", "throughput_tps", "compliance"]
TIER_MIN_AVAILABILITY = {"tier1": 99.95, "tier2": 99.9, "tier3": 99.5}


def all_submissions() -> list[dict]:
    """The seeded review queue plus the submissions people made (from the Blueprint Intelligence Studio). Persisted ones carry `arb_id`, because the saved-item store owns the key `id`."""
    saved = []
    for row in persist.list_items("arb_submission", 500):
        r = {k: v for k, v in row.items() if k not in ("id", "created_at")}
        r["id"] = r.pop("arb_id")
        saved.append(r)
    return list(get_store().arb) + sorted(saved, key=lambda r: r["id"])


def get_submission(sub_id: str) -> dict | None:
    return next((a for a in all_submissions() if a["id"] == sub_id), None)


def review(sub: dict) -> dict:
    s = get_store()
    design = dict(name=sub["title"], components=sub["components"], format="json")
    std = standards.check_design(design)
    findings: list[dict] = []

    def add(source, severity, title, recommendation, evidence):
        findings.append(dict(source=source, severity=severity, title=title, recommendation=recommendation, evidence=evidence))

    # --- standards findings
    for r in std["results"]:
        if r["status"] == "pass":
            continue
        sev = r["severity"] if r["status"] == "fail" else ("low" if r["severity"] in ("low", "info") else "medium")
        if sev == "info":
            sev = "low"
        add("standards", sev, f"{r['standard_id']}: {r['title']}", r["remediation"] or r["statement"],
            [dict(kind="standard", id=r["standard_id"], label=r["rationale"])])

    # --- NFR coverage
    nfr = sub.get("nfr", {})
    present = [k for k in REQUIRED_NFR if nfr.get(k) not in (None, "", [])]
    missing = [k for k in REQUIRED_NFR if k not in present]
    coverage = round(100 * len(present) / len(REQUIRED_NFR))
    for k in missing:
        add("nfr", "medium" if k in ("rto_hours", "rpo_minutes", "availability") else "low", f"NFR not stated: {k.replace('_', ' ')}",
            f"Declare a measurable {k.replace('_', ' ')} target and show how the design meets it.", [dict(kind="rule", id="STD-RES-003", label="RTO/RPO and NFRs must be declared")])
    tier = sub.get("tier", "tier2")
    try:
        avail = float(nfr.get("availability", 0))
    except ValueError:
        avail = 0
    if avail and avail < TIER_MIN_AVAILABILITY[tier]:
        add("nfr", "high", f"Availability target {avail}% is below the {tier} minimum of {TIER_MIN_AVAILABILITY[tier]}%", "Raise the target or re-tier the workload.", [dict(kind="rule", id="STD-RES-001", label=tier)])
    comps = sub["components"]
    if tier == "tier1" and any(c.get("instances", 2) < 2 for c in comps if c["type"] in ("aks_cluster", "app_service")):
        add("nfr", "high", "Tier-1 compute runs as a single instance", "Run at least two instances across availability zones.", [dict(kind="rule", id="STD-RES-004", label="No single instance for tier-1")])
    if nfr.get("rpo_minutes") is not None and nfr["rpo_minutes"] <= 5 and not any(c.get("multi_az") for c in comps):
        add("nfr", "medium", f"RPO of {nfr['rpo_minutes']} minutes is not supported by the declared topology", "Add zone-redundant replication or relax the RPO.", [dict(kind="rule", id="STD-RES-002", label="Backups and replication")])

    # --- estate risk from linked applications
    app_ids = set(sub["linked_apps"])
    risks = []
    for f in assessment.findings():
        hit = app_ids & {a["id"] for a in f["affected"]}
        if hit and f["severity"] in ("critical", "high"):
            risks.append(dict(finding_id=f["id"], title=f["title"], severity=f["severity"], linked=sorted(hit)))
    risks = sorted(risks, key=lambda r: SEV_ORDER[r["severity"]])[:5]
    for r in risks[:3]:
        add("risk", "medium", f"Linked estate risk: {r['title']}", "Confirm the design does not deepen this dependency and note a remediation date.", [dict(kind="finding", id=r["finding_id"], label=r["title"])])

    # --- pattern alignment
    styles = {c.get("style") for c in comps if c["type"] == "integration"}
    patterns = [dict(pattern="API-led connectivity", aligned=any(c["type"] in ("api", "api_management") for c in comps) and "direct_db" not in styles),
                dict(pattern="Event-driven architecture", aligned=any(c["type"] in ("kafka", "event_hub") for c in comps)),
                dict(pattern="Zero-trust private connectivity", aligned=not any(c.get("public_network_access") is True for c in comps))]

    findings.sort(key=lambda f: SEV_ORDER[f["severity"]])
    for n, f in enumerate(findings, 1):
        f["id"] = f"RF-{n:02d}"
    penalty = sum(SEV_PEN[f["severity"]] for f in findings)
    risk_penalty = min(40, sum(SEV_PEN[r["severity"]] for r in risks) * 1.2)
    readiness = max(0, round(0.45 * std["score"] + 0.25 * coverage + 0.30 * (100 - risk_penalty) - penalty * 0.25))
    crit = sum(f["severity"] == "critical" for f in findings)
    verdict = "no_go" if (crit or readiness < 55) else "conditional" if readiness < 80 or any(f["severity"] == "high" for f in findings) else "go"
    conditions = [f"{f['title']}: {f['recommendation']}" for f in findings if f["severity"] in ("critical", "high")][:6]
    return dict(submission_id=sub["id"], title=sub["title"], domain=sub["domain"], findings=findings, standards=std, nfr_coverage=dict(percent=coverage, present=present, missing=missing, values=nfr),
                risks=risks, patterns=patterns, readiness=readiness, verdict=verdict, conditions=conditions,
                counts={k: sum(f["severity"] == k for f in findings) for k in SEV_ORDER})
