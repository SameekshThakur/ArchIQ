"""Document intelligence engine. # MOCK: lexicon + pattern extraction standing in for an LLM reader.

Extracts entities (lexicon match against the asset catalog) and relations (sentence patterns) from the
architecture documents, detects conflicts between documents, finds gaps against the estate graph and
reconstructs a Mermaid diagram.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from functools import lru_cache

from app.repositories import persist
from app.repositories.store import get_store

REL_PHRASES = {
    "hosted_on": "is hosted on",
    "stores_in": "stores its data in",
    "reads_from": "reads from",
    "calls": "calls",
    "integrates": "integrates with",
    "system_of_record": "is the system of record for",
}
REL_LABEL = {"hosted_on": "hosted on", "stores_in": "stores data in", "reads_from": "reads from", "calls": "calls", "integrates": "integrates with", "system_of_record": "system of record for"}
_REL_RE = re.compile(r"^(?P<s>.+?) (?P<r>is hosted on|stores its data in|reads from|integrates with|is the system of record for|calls) (?P<o>.+)$")
_PHRASE_TO_REL = {v: k for k, v in REL_PHRASES.items()}
HOSTS = ["Azure AKS", "Azure App Service", "on-premises WebSphere", "on-premises Windows Server", "on-premises Linux servers", "the z/OS mainframe", "the vendor-hosted SaaS tenant"]
STATUS_WEIGHT = {"approved": 1.0, "current": 0.9, "accepted": 0.9, "proposed": 0.5, "draft": 0.4, "superseded": 0.1, "outdated": 0.1}
STALE_DAYS = 540

_uploaded: list[dict] = []
_version = [0]  # bumped whenever the corpus changes; keys the caches below


# ----------------------------------------------------------------- lexicon
@lru_cache
def _lexicon_cache(n_uploaded: int) -> tuple[re.Pattern, dict[str, dict]]:  # noqa: ARG001
    s = get_store()
    lex: dict[str, dict] = {}
    for a in s.apps:
        lex[a["name"]] = dict(kind="application", id=a["id"])
    for d in s.dbs:
        lex[d["name"]] = dict(kind="database", id=d["id"])
    for api in s.apis:
        if api["version"] == "v1":
            lex[api["name"]] = dict(kind="api", id=api["id"])
        lex[f"{api['name']} {api['version']}"] = dict(kind="api", id=api["id"])
    for t in s.technologies:
        lex.setdefault(t, dict(kind="technology", id=None))
    for h in HOSTS:
        lex.setdefault(h, dict(kind="host", id=None))
    names = sorted(lex, key=len, reverse=True)
    pat = re.compile(r"(?<![\w])(" + "|".join(re.escape(n) for n in names) + r")(?![\w])")
    return pat, lex


def _lexicon():
    return _lexicon_cache(_version[0])


def _all_docs() -> list[dict]:
    return get_store().documents + _uploaded


def _doc(doc_id: str) -> dict | None:
    return next((d for d in _all_docs() if d["id"] == doc_id), None)


def _status(doc: dict) -> str:
    m = re.search(r"^Status:\s*([A-Za-z]+)", doc["text"], re.M)
    return (m.group(1) if m else "Current").title()


def _age_days(doc: dict) -> int:
    s = get_store()
    ref = s.ref_date.replace(tzinfo=None)
    return max(0, (ref - datetime.fromisoformat(doc["updated_at"]).replace(tzinfo=None)).days)


def is_stale(doc: dict) -> bool:
    return _status(doc).lower() in ("outdated", "superseded") or _age_days(doc) > STALE_DAYS


# ------------------------------------------------------------- extraction
def extract_entities(text: str) -> list[dict]:
    pat, lex = _lexicon()
    found: dict[str, dict] = {}
    for m in pat.finditer(text):
        name = m.group(1)
        e = found.setdefault(name, dict(text=name, **lex[name], count=0, mentions=[]))
        e["count"] += 1
        e["mentions"].append([m.start(), m.end()])
    return sorted(found.values(), key=lambda e: (-e["count"], e["text"]))


def _resolve(name: str) -> dict:
    _, lex = _lexicon()
    name = name.strip().rstrip(".")
    if name in lex:
        return dict(name=name, **lex[name])
    return dict(name=name, kind="concept", id=None)


def extract_relations(doc: dict) -> list[dict]:
    out = []
    for line in doc["text"].splitlines():
        if not line.strip() or line.startswith(("#", "-", "`", "Status:", "DB_")):
            continue
        for sent in re.split(r"(?<=\.)\s+(?=[A-Z])", line.strip()):
            m = _REL_RE.match(sent.strip().rstrip("."))
            if not m:
                continue
            rel = _PHRASE_TO_REL[m["r"]]
            obj_txt, style = m["o"], None
            if rel == "integrates" and " using " in obj_txt:
                obj_txt, style = obj_txt.rsplit(" using ", 1)
            subj, obj = _resolve(m["s"]), _resolve(obj_txt)
            if subj["kind"] not in ("application", "database"):
                continue
            out.append(dict(subject=subj, rel=rel, label=REL_LABEL[rel], object=obj, style=style, sentence=sent.strip(), doc_id=doc["id"], doc_title=doc["title"]))
    return out


@lru_cache
def _corpus(n_uploaded: int) -> list[dict]:  # noqa: ARG001
    rels = []
    for d in _all_docs():
        st, age = _status(d), _age_days(d)
        for r in extract_relations(d):
            r.update(status=st, age_days=age, updated_at=d["updated_at"][:10])
            rels.append(r)
    return rels


def relations() -> list[dict]:
    return _corpus(_version[0])


# ------------------------------------------------------------ estate truth
def _host_phrase(a: dict) -> str:
    t = " ".join(a["tech"])
    if a["hosting"] == "mainframe":
        return "the z/OS mainframe"
    if a["hosting"] == "saas":
        return "the vendor-hosted SaaS tenant"
    if a["hosting"] == "azure":
        return "Azure AKS" if a["kind"] in ("platform", "microservice") else "Azure App Service"
    if "WebSphere" in t:
        return "on-premises WebSphere"
    if "Windows" in t:
        return "on-premises Windows Server"
    return "on-premises Linux servers"


def estate_facts() -> list[dict]:
    """What the estate graph says is true, in the same shape as extracted relations."""
    s = get_store()
    db_by_key = {d["key"]: d for d in s.dbs}
    facts = []
    for a in s.apps:
        facts.append(dict(subject=a["id"], rel="hosted_on", object=_host_phrase(a), object_id=None))
        db = db_by_key.get(a["db_key"]) if a["db_key"] else None
        if db:
            facts.append(dict(subject=a["id"], rel="stores_in", object=db["name"], object_id=db["id"]))
    for u in s.uses_extra:
        facts.append(dict(subject=u["app_id"], rel="stores_in", object=s.name(u["db_id"]), object_id=u["db_id"]))
    for i in s.integrations:
        if i["source_kind"] != "app":
            continue
        if i["style"] == "direct_db":
            facts.append(dict(subject=i["source_id"], rel="reads_from", object=s.name(i["target_id"]), object_id=i["target_id"]))
        elif i["target_kind"] == "app":
            facts.append(dict(subject=i["source_id"], rel="integrates", object=s.name(i["target_id"]), object_id=i["target_id"]))
    for api in s.apis:
        for c in api["consumers"]:
            facts.append(dict(subject=c, rel="calls", object=f"{api['name']} {api['version']}", object_id=api["id"]))
    return facts


# --------------------------------------------------------------- conflicts
def _authority(r: dict) -> float:
    return round(STATUS_WEIGHT.get(r["status"].lower(), 0.5) * 0.7 + max(0.0, 1 - r["age_days"] / 1500) * 0.3, 3)


def _matches_estate(r: dict, facts: dict) -> bool | None:
    s = get_store()
    subj = r["subject"]["id"]
    if r["rel"] == "hosted_on":
        return facts.get((subj, "hosted_on")) == {r["object"]["name"]}
    if r["rel"] == "stores_in":
        have = facts.get((subj, "stores_in"))
        return None if not have else r["object"]["name"] in have
    if r["rel"] == "calls":
        obj = r["object"]
        return (subj, "calls", obj["id"]) in facts.get("_calls", set()) if obj["kind"] == "api" else None
    return None


@lru_cache
def _conflicts_cache(n_uploaded: int) -> list[dict]:  # noqa: ARG001
    s = get_store()
    facts: dict = defaultdict(set)
    calls = set()
    for f in estate_facts():
        if f["rel"] in ("hosted_on", "stores_in"):
            facts[(f["subject"], f["rel"])].add(f["object"])
        if f["rel"] == "calls":
            calls.add((f["subject"], "calls", f["object_id"]))
    facts["_calls"] = calls

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in relations():
        sid = r["subject"]["id"]
        if r["rel"] in ("hosted_on", "stores_in") and sid:
            groups[(sid, r["rel"], "")].append(r)
        elif r["rel"] == "calls" and r["object"]["kind"] == "api":
            api = s.by_id[r["object"]["id"]]
            groups[(sid, "calls", api["name"])].append(r)
        elif r["rel"] == "system_of_record":
            groups[("", "system_of_record", r["object"]["name"])].append(r)

    out = []
    for (sid, rel, key), rs in groups.items():
        by_val: dict[str, list[dict]] = defaultdict(list)
        for r in rs:
            val = r["subject"]["name"] if rel == "system_of_record" else r["object"]["name"]
            if rel == "calls":
                val = r["object"]["name"] + (" v1" if r["object"]["name"].endswith("API") else "")
            by_val[val].append(r)
        if len(by_val) < 2:
            continue
        if rel == "calls" and all(_matches_estate(max(items, key=_authority), facts) for items in by_val.values()):
            continue  # the app really does call both APIs: not a documentation conflict
        claims = []
        for val, items in by_val.items():
            best = max(items, key=_authority)
            claims.append(dict(value=val, doc_id=best["doc_id"], doc_title=best["doc_title"], status=best["status"], updated_at=best["updated_at"], authority=_authority(best),
                               sentence=best["sentence"], matches_estate=_matches_estate(best, facts), also_in=[x["doc_id"] for x in items if x["doc_id"] != best["doc_id"]]))
        claims.sort(key=lambda c: -c["authority"])
        matching = [c for c in claims if c["matches_estate"]]
        subj_name = s.name(sid) if sid else key
        if matching:
            rec = matching[0]
            rationale = f"{rec['value']} matches the deployed estate and is stated in a {rec['status'].lower()} document last reviewed {rec['updated_at']}."
            basis = "estate"
        elif rel == "stores_in" and facts.get((sid, "stores_in")):
            real = sorted(facts[(sid, "stores_in")])[0]
            rec = dict(value=real)
            rationale = f"Neither document is current. The estate shows {subj_name} using {real}; both documents should be corrected."
            basis = "estate"
        elif rel == "system_of_record":
            rec = claims[0]
            rationale = f"{rec['value']} is stated in the most authoritative document ({rec['status'].lower()}, reviewed {rec['updated_at']}); confirm with the design authority because the estate has three customer-master systems."
            basis = "document authority"
        else:
            rec = claims[0]
            rationale = f"{rec['value']} comes from the most recent {rec['status'].lower()} document; the others are {', '.join(sorted({c['status'].lower() for c in claims[1:]}))}."
            basis = "document authority"
        title = {
            "hosted_on": f"Where is {subj_name} hosted?",
            "stores_in": f"Which data store does {subj_name} use?",
            "calls": f"Which version of {key} does {subj_name} call?",
            "system_of_record": f"Which system is the system of record for {key}?",
        }[rel]
        sev = "high" if (rel in ("stores_in", "system_of_record") or (sid and s.by_id[sid]["criticality"] == "critical")) else "medium"
        out.append(dict(rel=rel, subject_id=sid or None, subject=subj_name, title=title, severity=sev, claims=claims, recommended=rec["value"], rationale=rationale, basis=basis,
                        doc_ids=sorted({c["doc_id"] for c in claims} | {i for c in claims for i in c["also_in"]})))
    order = {"high": 0, "medium": 1}
    out.sort(key=lambda c: (order[c["severity"]], c["title"]))
    for i, c in enumerate(out, 1):
        c["id"] = f"CF-{i:03d}"
    return out


def conflicts() -> list[dict]:
    return _conflicts_cache(_version[0])


# -------------------------------------------------------------------- gaps
@lru_cache
def _gaps_cache(n_uploaded: int) -> dict:  # noqa: ARG001
    s = get_store()
    documented = {(r["subject"]["id"], r["rel"], r["object"].get("id") or r["object"]["name"]) for r in relations()}
    documented_hosts = {(r["subject"]["id"], "hosted_on") for r in relations() if r["rel"] == "hosted_on"}
    mentioned = defaultdict(int)
    for d in _all_docs():
        for e in extract_entities(d["text"]):
            if e["id"]:
                mentioned[e["id"]] += 1

    per_app = defaultdict(lambda: [0, 0])
    gaps: list[dict] = []
    for f in estate_facts():
        a = s.by_id[f["subject"]]
        if f["rel"] == "hosted_on":
            ok = (a["id"], "hosted_on") in documented_hosts
        else:
            ok = (f["subject"], f["rel"], f["object_id"]) in documented or (f["subject"], "stores_in", f["object_id"]) in documented
        per_app[a["id"]][1] += 1
        per_app[a["id"]][0] += int(ok)
        if not ok and f["rel"] in ("stores_in", "reads_from"):
            db = s.by_id[f["object_id"]]
            crit = a["criticality"] in ("critical", "high")
            eol = db["lifecycle"] in ("eol", "extended")
            gaps.append(dict(kind="undocumented_dependency", severity="high" if (crit and eol) else "medium" if crit else "low", app_id=a["id"], app=a["name"], domain=a["domain"],
                             title=f"{a['name']} → {db['name']} is not documented",
                             detail=f"The estate graph shows {a['name']} {REL_LABEL[f['rel']]} {db['name']} ({db['engine']}), but no document records this dependency.",
                             rel=f["rel"], target_id=db["id"], target=db["name"], evidence_asset=db["id"]))
    for a in s.apps:
        if mentioned[a["id"]] == 0:
            gaps.append(dict(kind="no_documentation", severity="high" if a["criticality"] == "critical" else "medium" if a["criticality"] == "high" else "low", app_id=a["id"], app=a["name"], domain=a["domain"],
                             title=f"No architecture document mentions {a['name']}", detail=f"{a['name']} ({a['criticality']} criticality) is not referenced by any of the {len(_all_docs())} indexed documents.",
                             rel=None, target_id=None, target=None, evidence_asset=a["id"]))
    for d in _all_docs():
        if is_stale(d) and d["doc_type"] in ("HLD", "LLD"):
            gaps.append(dict(kind="stale_document", severity="medium", app_id=None, app=None, domain=d["domain"], title=f"{d['title']} is stale", detail=f"Status {_status(d).lower()}, last updated {d['updated_at'][:10]} ({_age_days(d)} days ago).",
                             rel=None, target_id=None, target=None, evidence_asset=d["id"], doc_id=d["id"]))
    order = {"high": 0, "medium": 1, "low": 2}
    kind_order = {"undocumented_dependency": 0, "no_documentation": 1, "stale_document": 2}
    gaps.sort(key=lambda g: (order[g["severity"]], kind_order[g["kind"]], (g["app"] or ""), g["title"]))
    # the story gap first: Policy Admin Core -> Policy Master DB
    gaps.sort(key=lambda g: 0 if (g["kind"] == "undocumented_dependency" and g["app"] == "Policy Admin Core" and g["target"] == "Policy Master DB") else 1)
    for i, g in enumerate(gaps, 1):
        g["id"] = f"GAP-{i:03d}"
    cov = {aid: (round(100 * ok / tot) if tot else 100) for aid, (ok, tot) in per_app.items()}
    return dict(gaps=gaps, coverage=cov)


def gaps() -> list[dict]:
    return _gaps_cache(_version[0])["gaps"]


def coverage() -> dict:
    s = get_store()
    cov = _gaps_cache(_version[0])["coverage"]
    by_domain: dict[str, list[int]] = defaultdict(list)
    for a in s.apps:
        by_domain[a["domain"]].append(cov.get(a["id"], 0))
    overall = round(sum(cov.get(a["id"], 0) for a in s.apps) / len(s.apps))
    return dict(overall=overall, by_domain=[dict(domain=d, coverage=round(sum(v) / len(v)), apps=len(v)) for d, v in sorted(by_domain.items())],
                by_app={a["id"]: cov.get(a["id"], 0) for a in s.apps})


# --------------------------------------------------------------- documents
def summary() -> dict:
    docs = _all_docs()
    st = defaultdict(int)
    for d in docs:
        st[_status(d)] += 1
    conf = conflicts()
    return dict(documents=len(docs), entities=len({e["id"] for d in docs for e in extract_entities(d["text"]) if e["id"]}), relations=len(relations()), conflicts=len(conf),
                gaps=len(gaps()), stale=sum(is_stale(d) for d in docs), coverage=coverage()["overall"], by_status=dict(st),
                by_source={k: sum(1 for d in docs if d["source"] == k) for k in sorted({d["source"] for d in docs})})


def list_documents() -> list[dict]:
    s = get_store()
    conf_by_doc: dict[str, int] = defaultdict(int)
    for c in conflicts():
        for d in c["doc_ids"]:
            conf_by_doc[d] += 1
    rel_by_doc: dict[str, int] = defaultdict(int)
    for r in relations():
        rel_by_doc[r["doc_id"]] += 1
    rows = []
    for d in _all_docs():
        ents = extract_entities(d["text"])
        owner = s.by_id.get(d["author_id"])
        rows.append(dict(id=d["id"], title=d["title"], doc_type=d["doc_type"], source=d["source"], domain=d["domain"], status=_status(d), updated_at=d["updated_at"][:10], age_days=_age_days(d),
                         stale=is_stale(d), author=owner["name"] if owner else d["author_id"], path=d["path"], tags=d["tags"], entities=len(ents), relations=rel_by_doc[d["id"]], conflicts=conf_by_doc[d["id"]],
                         uploaded=d["id"].startswith("UPL-")))
    return rows


def analyze(doc_id: str) -> dict | None:
    d = _doc(doc_id)
    if not d:
        return None
    s = get_store()
    ents = extract_entities(d["text"])
    rels = [r for r in relations() if r["doc_id"] == doc_id]
    app_ids = {e["id"] for e in ents if e["kind"] == "application"}
    cf = [c for c in conflicts() if doc_id in c["doc_ids"]]
    gp = [g for g in gaps() if g.get("app_id") in app_ids and g["kind"] == "undocumented_dependency" or g.get("doc_id") == doc_id]
    owner = s.by_id.get(d["author_id"])
    return dict(id=d["id"], title=d["title"], doc_type=d["doc_type"], source=d["source"], domain=d["domain"], status=_status(d), updated_at=d["updated_at"][:10], age_days=_age_days(d), stale=is_stale(d),
                author=owner["name"] if owner else d["author_id"], path=d["path"], tags=d["tags"], text=d["text"], adr=d.get("adr"), entities=ents, relations=rels, conflicts=cf, gaps=gp[:12],
                diagram=reconstruct(doc_ids=[doc_id]))


def _make_doc(n: int, title: str, text: str, doc_type: str, domain: str) -> dict:
    s = get_store()
    return dict(id=f"UPL-{n:03d}", title=title, doc_type=doc_type, source="sharepoint", domain=domain, author_id=s.owners[0]["id"], created_at=s.ref_date.isoformat(), updated_at=s.ref_date.isoformat(),
                path=f"/uploads/{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}", text=text, tags=["uploaded"], adr=None)


def ingest(title: str, text: str, doc_type: str = "Confluence", domain: str = "Integration & Platform") -> dict:
    """Add an uploaded document to the corpus, save it, and analyse it. Saved documents are reloaded on restart."""
    n = persist.add_upload(title, text, doc_type, domain)
    _uploaded.append(_make_doc(n, title, text, doc_type, domain))
    _version[0] += 1
    return analyze(f"UPL-{n:03d}")  # type: ignore[return-value]


def load_uploads() -> int:
    """Reload saved uploads at start-up."""
    _uploaded.clear()
    for n, d in persist.list_uploads():
        _uploaded.append(_make_doc(n, d["title"], d["text"], d["doc_type"], d["domain"]))
    _version[0] += 1
    return len(_uploaded)


def remove_upload(doc_id: str) -> bool:
    doc = next((d for d in _uploaded if d["id"] == doc_id), None)
    if not doc:
        return False
    _uploaded.remove(doc)
    persist.delete_upload(int(doc_id.split("-")[1]))
    _version[0] += 1
    return True


def reset_uploads() -> None:
    """Forget every saved user item (uploaded documents, ad-hoc reviews, imports), in memory and on disk."""
    _uploaded.clear()
    persist.clear_all()
    _version[0] += 1


def search(q: str, limit: int = 8) -> list[dict]:
    toks = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 2]
    if not toks:
        return []
    out = []
    for d in _all_docs():
        hay = (d["title"] + " " + d["text"]).lower()
        score = sum(hay.count(t) + (5 if t in d["title"].lower() else 0) for t in toks)
        if score:
            i = min((hay.find(t) for t in toks if hay.find(t) >= 0), default=0)
            snippet = d["text"][max(0, i - 60): i + 140].replace("\n", " ")
            out.append(dict(id=d["id"], title=d["title"], doc_type=d["doc_type"], status=_status(d), score=score, snippet=snippet))
    return sorted(out, key=lambda x: -x["score"])[:limit]


# ----------------------------------------------------------------- diagram
def _nid(kind: str, ident: str | None, name: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9]", "_", ident or f"{kind}_{name}")


def reconstruct(doc_ids: list[str] | None = None, focus: str | None = None, include_gaps: bool = True, max_edges: int = 28) -> str:
    """Mermaid flowchart rebuilt from extracted relations. Dotted = conflicting claim, red dotted = undocumented."""
    s = get_store()
    rels = relations()
    if doc_ids:
        rels = [r for r in rels if r["doc_id"] in doc_ids]
    elif focus:
        rels = [r for r in rels if focus in (r["subject"]["id"], r["object"].get("id"))]
    else:  # default view: the SAP -> MuleSoft -> Salesforce -> Snowflake chain as the integration HLD describes it
        chain = {s.app_by_key[k]["id"] for k in ("SAP", "MULE", "SFC", "SNOW") if k in s.app_by_key}
        northwind_rels = [r for r in rels if r["doc_title"].startswith("Finance and Customer Integration") and r["rel"] == "integrates" and r["subject"]["id"] in chain and r["object"].get("id") in chain]
        if northwind_rels:
            rels = northwind_rels
            include_gaps = False
    conflicted = {(c["subject_id"], c["rel"]) for c in conflicts() if c["subject_id"]}
    edges, nodes, seen = [], {}, set()

    def node(ent: dict) -> str:
        nid = _nid(ent["kind"], ent.get("id"), ent["name"])
        nodes.setdefault(nid, ent)
        return nid

    for r in rels:
        if r["rel"] == "hosted_on" and not (focus or doc_ids):
            continue
        key = (r["subject"]["id"], r["rel"], r["object"]["name"])
        if key in seen:
            continue
        seen.add(key)
        a, b = node(r["subject"]), node(r["object"])
        label = (r["style"] or REL_LABEL[r["rel"]]).replace("point-to-point", "p2p")
        edges.append((a, b, label, "dotted" if (r["subject"]["id"], r["rel"]) in conflicted else "solid"))
        if len(edges) >= max_edges:
            break
    if include_gaps:
        scope_ids = {n["id"] for n in nodes.values() if n.get("id")}
        for g in gaps():
            if g["kind"] == "undocumented_dependency" and g["app_id"] in scope_ids and len(edges) < max_edges + 6:
                a = node(dict(name=g["app"], kind="application", id=g["app_id"]))
                b = node(dict(name=g["target"], kind="database", id=g["target_id"]))
                edges.append((a, b, "undocumented", "gap"))
    lines = ["flowchart LR"]
    for nid, e in nodes.items():
        label = e["name"].replace('"', "'")
        shape = {"database": f'{nid}[("{label}")]', "api": f'{nid}{{{{"{label}"}}}}', "host": f'{nid}(["{label}"])', "technology": f'{nid}(["{label}"])', "concept": f'{nid}(["{label}"])'}.get(e["kind"], f'{nid}["{label}"]')
        lines.append("  " + shape)
    gap_idx = []
    for i, (a, b, label, style) in enumerate(edges):
        arrow = "-.->" if style in ("dotted", "gap") else "-->"
        lines.append(f'  {a} {arrow}|"{label}"| {b}')
        if style == "gap":
            gap_idx.append(str(i))
    if gap_idx:
        lines.append(f"  linkStyle {','.join(gap_idx)} stroke:#f43f5e,stroke-width:2px,color:#f43f5e")
    for nid, e in nodes.items():
        if e["kind"] == "database":
            lines.append(f"  style {nid} stroke:#8b5cf6")
    return "\n".join(lines)
