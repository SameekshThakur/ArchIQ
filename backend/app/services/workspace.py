"""The guided start: what the person is looking for, the documents they bring and the business domain, run end to end.

A workspace is the one analysis the app is currently showing. Until one exists (or the demo is loaded) every page shows an empty state. A run chains the
engines that already exist: read the files, add documents to the corpus, reconcile inventory exports, check infrastructure code and designs against
the standards, review designs, then put the domain's slice of the estate (assets, findings, documents) next to what was uploaded. Each step is saved as
it finishes so the page can show real progress.

The workspace is stored as a saved item, so it survives a restart. Only one is active at a time; each run is a separate saved item and replacing it
cleans up what the previous run added (documents, imports, reviews).
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from urllib.parse import quote
from collections import Counter
from typing import Any

from app.core.config import get_settings
from app.core.errors import ApiError
from app.mock_ai.generators import documents as docs
from app.mock_ai.rules import assessment
from app.mock_ai.rules import review as review_engine
from app.mock_ai.rules import standards as std
from app.repositories import persist
from app.repositories.store import get_store
from app.services import connections, inventory

log = logging.getLogger("archiq.workspace")
KIND = "workspace"

INTENTS: list[dict[str, str]] = [
    dict(id="understand", label="Understand what we have", hint="Pull the documents and inventory together and see how they match the estate", to="/discovery"),
    dict(id="review", label="Get a design ready for architecture review", hint="Check a design against the standards and get a go / no-go with reasons", to="/reviews"),
    dict(id="compliance", label="Check infrastructure code against standards", hint="Terraform, Bicep or a design file, scored rule by rule", to="/standards"),
    dict(id="risk", label="Find risks and technical debt", hint="Single points of failure, obsolete technology and where debt is building up", to="/assessment"),
    dict(id="modernize", label="Plan modernisation", hint="Where to start, in what order, and what it touches", to="/modernization"),
]
_KEYWORDS = {
    "review": ("review", "arb", "go/no-go", "readiness", "approve", "sign-off", "signoff"),
    "compliance": ("terraform", "bicep", "iac", "infrastructure", "standard", "policy", "complian", "baseline"),
    "risk": ("risk", "debt", "obsolete", "single point", "spof", "weak", "vulnerab", "resilien"),
    "modernize": ("moderni", "migrate", "migration", "cloud", "roadmap", "transform", "replace", "retire"),
    "understand": ("understand", "discover", "inventory", "cmdb", "what do we have", "map", "document", "estate"),
}
STEPS = [
    ("connect", "Reading connected tools"),
    ("read", "Reading your files"),
    ("documents", "Adding documents to the knowledge base"),
    ("inventory", "Reconciling inventory against the estate"),
    ("standards", "Checking designs and infrastructure code against standards"),
    ("review", "Reviewing designs for readiness"),
    ("estate", "Putting it next to the estate"),
    ("summary", "Preparing the results"),
]
MAX_DOCS = 12


def classify_intent(text: str, chosen: str | None = None) -> dict:
    by_id = {i["id"]: i for i in INTENTS}
    if chosen in by_id:
        return by_id[chosen]
    t = (text or "").lower()
    best = max(_KEYWORDS, key=lambda k: sum(w in t for w in _KEYWORDS[k]))
    return by_id[best if any(w in t for w in _KEYWORDS[best]) else "understand"]


def known_domains() -> list[dict]:
    s = get_store()
    c = Counter(a["domain"] for a in s.apps)
    return [dict(name=d, assets=n) for d, n in sorted(c.items())]


# ------------------------------------------------------------------ state
def _empty() -> dict:
    return dict(status="empty", mode=None, intent=None, domain=None, documents=[], steps=[], result=None, created=dict(docs=[], imports=[], reviews=[], syncs=[]), sources=[], error=None)


def _current() -> tuple[int | None, dict]:
    rows = persist.list_items(KIND, 1)
    if not rows:
        return None, _empty()
    r = rows[0]
    state = {k: v for k, v in r.items() if k not in ("id", "created_at")}
    return r["id"], state


def get() -> dict:
    n, state = _current()
    # a run that was interrupted by a restart can never finish: say so instead of showing progress forever
    if state["status"] == "running" and n is not None and n not in _live:
        state.update(status="failed", error="The analysis was interrupted (the server restarted). Start it again.")
        persist.update_item(KIND, n, state)
    return state


_live: set[int] = set()


def _cleanup(state: dict) -> None:
    c = state.get("created") or {}
    for doc_id in c.get("docs", []):
        docs.remove_upload(doc_id)
    for n in c.get("imports", []):
        persist.delete_item("import", n)
    for n in c.get("reviews", []):
        persist.delete_item("review", n)
    for n in c.get("syncs", []):
        persist.delete_item("connection_sync", n)


def reset() -> dict:
    """Start over: forget the analysis and everything it added."""
    n, state = _current()
    if n is not None:
        _cleanup(state)
        persist.delete_item(KIND, n)
    return _empty()


def load_demo() -> dict:
    reset()
    state = _empty()
    state.update(status="ready", mode="demo", intent=dict(id="understand", label="Explore the baseline estate", to="/"), domain=dict(name="All domains", known=True, all=True))
    persist.add_item(KIND, state)
    return state


# ------------------------------------------------------------------ the run
def start(intent_id: str | None, intent_text: str, domain: str, files_in: list[dict], sources: list[str] | None = None) -> dict:
    domain = (domain or "").strip()
    if len(domain) < 2:
        raise ApiError(422, "domain_required", "Choose a business domain, or add one")
    if len(files_in) > MAX_DOCS:
        raise ApiError(422, "too_many_files", f"Add at most {MAX_DOCS} files at a time")
    chosen: list[dict] = []
    for pid in dict.fromkeys(sources or []):  # keep the order, drop repeats
        if pid not in connections.CONNECTORS:
            raise ApiError(422, "unknown_connection", f"'{pid}' is not a platform ArchIQ can connect to")
        info = connections.public(pid)
        if not info["configured"]:
            raise ApiError(422, "connection_not_set_up", f"{info['name']} is not set up yet. Connect it first, or untick it")
        chosen.append(dict(id=pid, name=info["name"], mode=info["mode"]))
    n0, old = _current()
    if old["status"] == "running":
        raise ApiError(409, "already_running", "An analysis is already running")
    reset()
    intent = classify_intent(intent_text, intent_id)
    known = {d["name"] for d in known_domains()}
    state = _empty()
    state.update(status="running", mode="custom", intent=dict(id=intent["id"], label=intent["label"], text=(intent_text or "").strip()[:500], to=intent["to"]),
                 domain=dict(name=domain, known=domain in known), sources=chosen, documents=[dict(name=f["filename"], chars=len(f["text"])) for f in files_in],
                 steps=[dict(id=i, label=lbl, status="pending", detail="") for i, lbl in STEPS], started_at=time.time())
    n = persist.add_item(KIND, state)
    _live.add(n)
    threading.Thread(target=_run, args=(n, state, files_in), daemon=True, name=f"workspace-{n}").start()
    return state


def _step(n: int, state: dict, sid: str, status: str, detail: str = "", link: str | None = None) -> None:
    st = next(s for s in state["steps"] if s["id"] == sid)
    st.update(status=status, detail=detail)
    if link:
        st["link"] = link
    persist.update_item(KIND, n, state)


def _pace() -> None:
    # same simulated-AI pacing as the rest of the app (0 in tests), so people can follow the steps
    time.sleep(0.55 * get_settings().ai_latency)


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _run(n: int, state: dict, files_in: list[dict]) -> None:
    try:
        _execute(n, state, files_in)
    except Exception as e:  # noqa: BLE001 - whatever goes wrong must end up on the page, not in a log nobody reads
        log.exception("workspace run failed")
        state.update(status="failed", error=f"The analysis stopped: {e}")
        for s in state["steps"]:
            if s["status"] == "running":
                s["status"] = "failed"
        persist.update_item(KIND, n, state)
    finally:
        _live.discard(n)


def _execute(n: int, state: dict, files_in: list[dict]) -> None:
    domain = state["domain"]["name"]
    created = state["created"]
    roles: dict[str, list[dict]] = {"inventory": [], "iac": [], "design": [], "document": []}

    # 0 connect: read the chosen tools; what they bring joins what the files bring
    pulled = _pull_connections(n, state)

    # 1 read: decide what each file is
    _step(n, state, "read", "running")
    _pace()
    for f, meta in zip(files_in, state["documents"]):
        name, text, ext = f["filename"], f["text"], _ext(f["filename"])
        role = "document"
        inv = None
        if ext in ("csv", "tsv", "xlsx"):
            try:
                inv = inventory.reconcile(name, text)
                role = "inventory"
            except ApiError:
                inv = None
        if role != "inventory":
            try:
                parsed = std.parse_design(text)
            except ApiError:
                parsed = {"components": [], "format": "text"}
            comps = len(parsed.get("components", []))
            if ext in ("tf", "tfvars", "bicep") or (parsed.get("format") not in ("text", None) and comps):
                role = "iac"
            elif comps >= 3:
                role = "design"
            meta["components"] = comps
        meta.update(role=role)
        roles[role].append(dict(name=name, text=text, reconciled=inv))
    kinds = Counter(m["role"] for m in state["documents"])
    _step(n, state, "read", "done", ", ".join(f"{c} {lbl}{'' if c == 1 else 's'}" for lbl, c in (("inventory export", kinds["inventory"]), ("infrastructure code file", kinds["iac"]), ("design", kinds["design"]), ("document", kinds["document"])) if c) or ("no files supplied" if pulled["read"] else "no files supplied, using the estate only"))

    # 2 documents
    ingested: list[dict] = list(pulled["ingested"])
    to_ingest = roles["document"] + roles["design"]
    if to_ingest or ingested:
        _step(n, state, "documents", "running")
        _pace()
        for f in to_ingest:
            title = re.sub(r"[_-]+", " ", f["name"].rsplit(".", 1)[0]) if len(f["name"]) > 3 else "Uploaded document"
            if len(f["text"].strip()) < 20:
                continue
            a = docs.ingest(title[:200] if len(title) >= 3 else "Uploaded document", f["text"], "HLD" if "hld" in f["name"].lower() else "Confluence", domain)
            created["docs"].append(a["id"])
            ingested.append(a)
        conflicts = sum(len(a.get("conflicts", []) or []) for a in ingested)
        gaps = sum(len(a.get("gaps", []) or []) for a in ingested)
        ents = sum(len(a.get("entities", []) or []) for a in ingested)
        _step(n, state, "documents", "done", f"{len(ingested)} added, {ents} assets recognised, {conflicts} conflicts, {gaps} gaps", "/documents")
    else:
        _step(n, state, "documents", "skipped", "no documents supplied")

    # 3 inventory
    recon: list[dict] = list(pulled["recon"])
    if roles["inventory"] or recon:
        _step(n, state, "inventory", "running")
        _pace()
        for f in roles["inventory"]:
            r = f["reconciled"]
            r["saved_id"] = persist.add_item("import", dict(r))
            created["imports"].append(r["saved_id"])
            recon.append(r)
        m = sum(r["matched"] for r in recon)
        c = sum(r["conflicts"] for r in recon)
        _step(n, state, "inventory", "done", f"{sum(r['rows'] for r in recon)} rows: {m} matched, {c} with conflicting details, {sum(r['new'] for r in recon)} not in the estate", "/discovery")
    else:
        _step(n, state, "inventory", "skipped", "no inventory export supplied")

    # 4 standards
    checks: list[dict] = list(pulled["checks"])
    checkable = roles["iac"] + roles["design"]
    if checkable or checks:
        _step(n, state, "standards", "running")
        _pace()
        for f in checkable:
            parsed = std.parse_design(f["text"])
            if not parsed["components"]:
                continue
            res = std.check_design(parsed, None)
            checks.append(dict(name=f["name"], format=res["format"], components=res["components"], passed=res["passed"], warned=res["warned"], failed=res["failed"],
                               headlines=[r["headline"] for r in res["results"] if r["status"] == "fail" and r.get("headline")][:3] or [f"{r['standard_id']}: {r['title']}" for r in res["results"] if r["status"] == "fail"][:3]))
        _step(n, state, "standards", "done", f"{len(checks)} checked: " + ", ".join(f"{c['failed']} failed" for c in checks[:3]) if checks else "nothing checkable found", "/standards")
    else:
        _step(n, state, "standards", "skipped", "no design or infrastructure code supplied")

    # 5 review
    reviews: list[dict] = []
    if checkable:
        _step(n, state, "review", "running")
        _pace()
        for f in checkable[:3]:
            parsed = std.parse_design(f["text"])
            if not parsed["components"]:
                continue
            title = f["name"].rsplit(".", 1)[0][:120]
            sub = dict(id="ADHOC", title=title, domain=domain, tier="tier2", nfr=parsed.get("nfr", {}), components=parsed["components"], linked_apps=[], summary="Guided analysis", stage="draft", submitter="You", submitted_at="", arb_date="")
            r = review_engine.review(sub)
            req = dict(title=title, domain=domain, tier="tier2", design=f["text"], nfr=parsed.get("nfr", {}))
            sid = persist.add_item("review", dict(request=req, title=title, tier="tier2", verdict=r["verdict"], readiness=r["readiness"]))
            created["reviews"].append(sid)
            reviews.append(dict(name=f["name"], saved_id=sid, verdict=r["verdict"], readiness=r["readiness"], counts=r["counts"], top=[x["title"] for x in r["findings"][:3]]))
        _step(n, state, "review", "done", ", ".join(f"{x['name']}: {x['verdict'].replace('_', ' ')}" for x in reviews[:3]) or "nothing to review", "/reviews")
    else:
        _step(n, state, "review", "skipped", "no design supplied")

    # 6 estate
    _step(n, state, "estate", "running")
    _pace()
    s = get_store()
    apps = [a for a in s.apps if a["domain"] == domain]
    findings = [f for f in assessment.findings() if domain in f["domains"]]
    sev = Counter(f["severity"] for f in findings)
    corpus = [d for d in docs.list_documents() if d["domain"] == domain and not d["id"].startswith("UPL-")]
    estate = dict(assets=len(apps), critical_assets=sum(1 for a in apps if a["criticality"] == "critical"), findings=len(findings), by_severity=dict(sev),
                  top_findings=[f["title"] for f in sorted(findings, key=lambda f: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(f["severity"], 4), -f["affected_count"]))[:4]], documents=len(corpus))
    _step(n, state, "estate", "done", (f"{len(apps)} applications, {len(findings)} findings in {domain}" if apps else f"nothing in the estate is tagged to {domain}"), f"/graph?domain={quote(domain)}" if apps else None)

    # 7 summary
    _step(n, state, "summary", "running")
    _pace()
    state["result"] = _summarise(state, ingested, recon, checks, reviews, estate, pulled)
    state["status"] = "ready"
    state["finished_at"] = time.time()
    _step(n, state, "summary", "done", "ready")


def _pull_connections(n: int, state: dict) -> dict:
    """Read each chosen platform the same way its Connections card does, and hand the results to the steps that follow.

    A platform that cannot be read is reported and skipped; it never stops the analysis.
    """
    out: dict[str, Any] = dict(recon=[], ingested=[], checks=[], work=[], read=[], failed=[])
    chosen = state.get("sources") or []
    if not chosen:
        _step(n, state, "connect", "skipped", "no connected tools chosen")
        return out
    _step(n, state, "connect", "running")
    created = state["created"]
    for src in chosen:
        _pace()
        name = src["name"]
        started = time.time()
        try:
            mode, data, err = connections.fetch(src["id"])
            run = asyncio.run(connections.apply(src["id"], mode, data, err, started))
        except Exception as e:  # noqa: BLE001 - one tool failing must not stop the others
            out["failed"].append(f"{name}: {e}")
            continue
        if run.get("id") is not None:
            created.setdefault("syncs", []).append(run["id"])
        if not run.get("ok"):
            out["failed"].append(f"{name}: {run.get('error') or 'could not be read'}")
            persist.update_item(KIND, n, state)
            continue
        created["docs"].extend(run.get("doc_ids", []))
        if run.get("import_id") is not None:
            created["imports"].append(run["import_id"])
            rep = persist.get_item("import", run["import_id"])
            if rep:
                out["recon"].append(rep)
        for d in run.get("doc_ids", []):
            a = docs.analyze(d)
            if a:
                out["ingested"].append(a)
        st = run.get("standards")
        if st:
            out["checks"].append(dict(name=name, format=src["id"], components=st.get("components", 0), passed=st.get("passed", 0), warned=st.get("warned", 0), failed=st.get("failed", 0),
                                      headlines=[f"{t['standard_id']}: {t['title']}" for t in st.get("top", [])][:3]))
        if run.get("work") is not None and any(m["label"] == "Open items" for m in run.get("metrics", [])):
            out["work"].append(dict(platform=name, open=next(m["value"] for m in run["metrics"] if m["label"] == "Open items"), per=run["work"]))
        out["read"].append(dict(name=name, mode=run.get("mode", mode), records=run.get("record_count", 0), headline=run.get("headline", "")))
        persist.update_item(KIND, n, state)
    parts = [f"{r['name']} ({'not live' if r['mode'] == 'demo' else 'live'}): {r['records']} records" for r in out["read"]]
    if out["failed"]:
        parts += [f"could not read {f}" for f in out["failed"]]
    _step(n, state, "connect", "failed" if not out["read"] else "done", "; ".join(parts))
    return out


def _summarise(state: dict, ingested: list[dict], recon: list[dict], checks: list[dict], reviews: list[dict], estate: dict, pulled: dict | None = None) -> dict:
    domain = state["domain"]["name"]
    intent = state["intent"]
    sections: list[dict[str, Any]] = []
    notes: list[str] = []
    if not state["domain"]["known"]:
        notes.append(f"“{domain}” is a new domain, so nothing in the estate is tagged to it. Your documents are filed under it, and estate numbers below are zero.")
    pulled = pulled or dict(read=[], failed=[], work=[])
    if not state["documents"] and not pulled["read"]:
        notes.append("No files or connected tools were added, so this shows the estate for the domain only.")
    for f in pulled["failed"]:
        notes.append(f"Could not read {f}. The analysis went on without it.")

    if ingested:
        conflicts = sum(len(a.get("conflicts", []) or []) for a in ingested)
        gaps = sum(len(a.get("gaps", []) or []) for a in ingested)
        sections.append(dict(id="documents", title="Documents", to="/documents", metrics=[dict(label="Added", value=len(ingested)), dict(label="Conflicts", value=conflicts), dict(label="Gaps vs estate", value=gaps)],
                             bullets=[f"{a['title']}: {len(a.get('entities', []) or [])} assets recognised" for a in ingested[:4]]))
    if recon:
        sections.append(dict(id="inventory", title="Inventory", to="/discovery", metrics=[dict(label="Rows", value=sum(r["rows"] for r in recon)), dict(label="Matched", value=sum(r["matched"] for r in recon)),
                                                                                     dict(label="Conflicts", value=sum(r["conflicts"] for r in recon)), dict(label="New", value=sum(r["new"] for r in recon)),
                                                                                     dict(label="Missing from export", value=sum(len(r["missing"]) for r in recon))],
                             bullets=[f"{r['filename']}: columns mapped {', '.join(r['columns'])}" for r in recon[:2]]))
    if checks:
        sections.append(dict(id="standards", title="Standards", to="/standards", metrics=[dict(label="Passed", value=sum(c["passed"] for c in checks)), dict(label="Warnings", value=sum(c["warned"] for c in checks)), dict(label="Failed", value=sum(c["failed"] for c in checks))],
                             bullets=[f"{c['name']}: {h}" for c in checks for h in c["headlines"]][:5]))
    if reviews:
        sections.append(dict(id="reviews", title="Readiness reviews", to="/reviews", metrics=[dict(label=r["name"], value=r["verdict"].replace("_", " ")) for r in reviews],
                             bullets=[f"{r['name']}: {t}" for r in reviews for t in r["top"]][:6]))
    if pulled["read"]:
        sections.append(dict(id="sources", title="Connected tools", to="/connections", metrics=[dict(label=r["name"], value=f"{r['records']} records") for r in pulled["read"]],
                             bullets=[f"{r['name']}: {'not live' if r['mode'] == 'demo' else 'live'}" for r in pulled["read"]]))
    for w in pulled["work"]:
        per = w["per"]
        sections.append(dict(id="work", title=f"Open work in {w['platform']}", to="/connections", metrics=[dict(label="Open items", value=w["open"]), dict(label="Applications linked", value=len(per))],
                             bullets=[f"{e['app']}: {e['open']} open, {e['done']} done" for e in per[:6]]))
    sections.append(dict(id="estate", title=f"{domain} in the estate", to=f"/graph?domain={quote(domain)}" if estate["assets"] else "/graph",
                         metrics=[dict(label="Applications", value=estate["assets"]), dict(label="Critical", value=estate["critical_assets"]), dict(label="Findings", value=estate["findings"]), dict(label="Existing documents", value=estate["documents"])],
                         bullets=estate["top_findings"]))

    verdicts = [r["verdict"] for r in reviews]
    worst = "no_go" if "no_go" in verdicts else ("conditional" if any(v not in ("go", "approved") for v in verdicts) else ("go" if verdicts else None))
    bits = []
    if reviews:
        bits.append(f"{len(reviews)} design{'s' if len(reviews) != 1 else ''} reviewed, overall {worst.replace('_', ' ') if worst else 'n/a'}")
    if checks:
        bits.append(f"{sum(c['failed'] for c in checks)} standards failures")
    if recon:
        bits.append(f"{sum(r['conflicts'] for r in recon)} inventory conflicts")
    if pulled["read"]:
        bits.append(f"{len(pulled['read'])} connected tool{'s' if len(pulled['read']) != 1 else ''} read")
    if estate["assets"]:
        bits.append(f"{estate['findings']} findings across {estate['assets']} {domain} applications")
    headline = ("; ".join(bits)[:1].upper() + "; ".join(bits)[1:] + ".") if bits else f"Nothing to analyse yet for {domain}."
    return dict(headline=headline, verdict=worst, sections=sections, notes=notes, primary=dict(label="Open the main view", to=intent["to"]))
