"""Blueprint Intelligence Studio: saved designs, versions, decisions and the hand-off to the architecture review queue.

A design is stored as its inputs (requirements, blueprint, choices, edits, decisions) in the existing saved-item store. The diagram and every validation result are recomputed from those
inputs whenever they are needed, so a result can never be out of date with the design it describes.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from typing import Any

from app.core.errors import BadRequest, NotFound
from app.mock_ai.generators import blueprints as bp_gen
from app.mock_ai.generators import studio_catalog as cat
from app.mock_ai.generators import studio_export as export
from app.mock_ai.rules import review as review_engine
from app.mock_ai.rules import studio as engine
from app.mock_ai.rules import studio_requirements as reqs
from app.repositories import persist
from app.repositories.store import get_store
from app.services.ai import narrate

KIND = "studio_design"
SUBMISSION_KIND = "arb_submission"
MAX_VERSIONS = 50
MAX_OPS = 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ref(n: int) -> str:
    return f"DSG-{n:04d}"


# ------------------------------------------------------------------ storage
def _load(n: int) -> dict:
    row = persist.get_item(KIND, n)
    if not row:
        raise NotFound(f"Design {n} not found")
    d = {k: v for k, v in row.items() if k not in ("id", "created_at")}
    d["n"] = n
    d["ref"] = ref(n)
    d["created_at"] = row["created_at"]
    return d


def _save(d: dict) -> None:
    payload = {k: v for k, v in d.items() if k not in ("n", "ref", "created_at")}
    payload["updated_at"] = _now()
    persist.update_item(KIND, d["n"], payload)


def _event(d: dict, what: str, note: str = "") -> None:
    d.setdefault("workflow", []).append(dict(at=_now(), event=what, note=note))
    d["workflow"] = d["workflow"][-200:]


def _inputs(d: dict) -> dict:
    return dict(blueprint_id=d["blueprint_id"], selections=d["selections"], nfr=d["nfr"], ops=d["ops"], linked_apps=d["linked_apps"])


def _apply_inputs(d: dict, inp: dict) -> None:
    for k in ("selections", "nfr", "ops", "linked_apps"):
        d[k] = inp[k]


def _req_view(d: dict) -> dict:
    ext = dict(d.get("extraction") or {})
    ranked = (d.get("recommendation") or {}).get("ranked") or []
    mine = next((r for r in ranked if r["id"] == d["blueprint_id"]), None)
    ext["matched_signals"] = [m["label"] for m in (mine or {}).get("matched", [])]
    return ext


def status_of(d: dict) -> str:
    if not d.get("blueprint_id"):
        return "draft"
    h = engine.inputs_hash(_inputs(d))
    sub = d.get("submission")
    if sub:
        return "submitted" if sub["hash"] == h else "changed_after_submission"
    if (d.get("validation") or {}).get("hash") == h:
        return "validated"
    return "draft"


# ------------------------------------------------------------------ the design as a whole
def compute(d: dict) -> tuple[dict | None, dict | None]:
    if not d.get("blueprint_id"):
        return None, None
    arch = engine.build(d["blueprint_id"], d["selections"], d["ops"], d["nfr"], _req_view(d))
    val = engine.validate(arch, d["nfr"], d["selections"].get("tier", "tier2"), d["linked_apps"], d["title"], d.get("domain") or "", _req_view(d), d.get("decisions"))
    resolved = [dict(id=gid, status=x["status"], fix_label=x.get("fix_label"), at=x["at"]) for gid, x in (d.get("decisions") or {}).items() if x["status"] in ("accepted", "modified") and gid not in {g["id"] for g in val["gaps"]}]
    val["resolved"] = resolved
    return arch, val


def view(n: int) -> dict:
    d = _load(n)
    arch, val = compute(d)
    out = {k: v for k, v in d.items() if k not in ("recommendation",)}
    rec = d.get("recommendation") or {}
    out["recommendation"] = {k: v for k, v in rec.items() if k != "ranked"}
    out["ranking"] = [dict(id=r["id"], name=r["name"], score=r["score"]) for r in rec.get("ranked", [])]
    out["status"] = status_of(d)
    out["architecture"] = arch
    out["validation"] = val
    out["recorded_validation"] = d.get("validation")
    out["checks"] = submission_checks(d, val) if val else []
    out["export"] = export_preview(d, arch, val) if arch else None
    out["versions"] = [{k: v for k, v in x.items() if k not in ("inputs",)} for x in d.get("versions", [])]
    return out


def list_designs() -> list[dict]:
    rows = []
    for r in persist.list_items(KIND, 200):
        d = {k: v for k, v in r.items() if k not in ("id", "created_at")}
        d["n"], d["ref"], d["created_at"] = r["id"], ref(r["id"]), r["created_at"]
        rows.append(dict(n=d["n"], ref=d["ref"], title=d["title"], domain=d.get("domain"), blueprint_id=d.get("blueprint_id"), status=status_of(d), created_at=d["created_at"], updated_at=d.get("updated_at"),
                         versions=len(d.get("versions", [])), arb_id=(d.get("submission") or {}).get("arb_id"), readiness=(d.get("validation") or {}).get("readiness"), verdict=(d.get("validation") or {}).get("verdict")))
    return rows


def delete(n: int) -> None:
    d = _load(n)
    if d.get("submission"):
        raise BadRequest(f"{d['ref']} was submitted as {d['submission']['arb_id']}. A submitted design cannot be deleted; it is part of the review record.")
    persist.delete_item(KIND, n)


# ------------------------------------------------------------------ steps 1 and 2: requirements and recommendation
async def analyse_text(text: str, domain: str | None) -> dict:
    text = (text or "").strip()
    if len(text) < 20:
        raise BadRequest("Describe the requirements in at least a sentence or two (20 characters or more).")
    if len(text) > 20000:
        raise BadRequest("The requirements are longer than 20,000 characters. Summarise them, or keep the key sections.")
    extraction = reqs.extract(text, domain)
    rec = reqs.recommend(extraction)
    ai_req = await narrate("studio.requirements", dict(words=extraction["words"], found=6 - len(extraction["nfr_missing"]), present=[k.replace("_", " ") for k in extraction["nfr_present"]], missing=[k.replace("_", " ") for k in extraction["nfr_missing"]],
                                                       tier=extraction["tier"], exposure=extraction["exposure"], classification=extraction["classification"], systems=[x["name"] for x in extraction["systems"]]),
                           [("Read the text", f"{extraction['words']} words", 120), ("Find targets and constraints", f"{len(extraction['facts'])} facts with evidence", 260), ("Match estate systems", f"{len(extraction['systems'])} found", 160)],
                           [("rule", f["key"], f["label"]) for f in extraction["facts"][:6]], 0.86)
    ai_rec = await _narrate_recommendation(rec)
    return dict(extraction=extraction, recommendation=rec, ai=dict(requirements=ai_req, recommendation=ai_rec))


async def _narrate_recommendation(rec: dict) -> dict:
    r = rec["recommended"]
    facts = dict(name=r["name"] if r else None, score=r["score"] if r else 0, reasons=[m["label"] for m in (r["rationale"] if r else [])][:4], alt=(rec["alternatives"][0]["name"] if rec["alternatives"] and r else None),
                 alt_score=(rec["alternatives"][0]["score"] if rec["alternatives"] else 0), combine=(rec["combine"][0]["reason"] if rec["combine"] else ""), watch=(r["watch_outs"][0] if r and r["watch_outs"] else ""),
                 closest=[a["name"] for a in rec["alternatives"]], threshold=rec["threshold"])
    return await narrate("studio.recommendation", facts, [("Score the 12 blueprints", "weighted cues, tags and use-case overlap", 240), ("Rank and compare", "margin between first and second", 140), ("Explain the choice", "evidence per cue", 180)],
                         [("pattern", a["id"], a["name"]) for a in ([dict(id=r["id"], name=r["name"])] if r else []) + rec["alternatives"]][:5], r["confidence"] if r else 0.3)


async def create(text: str, title: str | None, domain: str | None, owner: str | None) -> dict:
    res = await analyse_text(text, domain)
    ext, rec = res["extraction"], res["recommendation"]
    name = (title or "").strip() or _title_from(text, ext["domain"]["value"] or domain, rec["recommended"]["name"] if rec["recommended"] else None)
    d: dict[str, Any] = dict(title=name[:120], domain=(ext["domain"]["value"] or domain or ""), owner=(owner or "").strip() or "You", requirement=dict(text=ext["text"]), extraction=ext, recommendation=rec, ai=res["ai"],
                             blueprint_id=None, blueprint_choice=None, selections={}, selection_sources={}, nfr={}, nfr_origin={}, ops=[], linked_apps=[x["id"] for x in ext["systems"]], decisions={}, versions=[], validation=None, submission=None, workflow=[])
    n = persist.add_item(KIND, d)
    d["n"], d["ref"] = n, ref(n)
    _event(d, "Requirements analysed", f"{len(ext['facts'])} facts found")
    if rec["recommended"]:
        _choose(d, rec["recommended"]["id"], overridden=False, reason="")
    _save(d)
    return view(n)


def _title_from(text: str, domain: str | None = None, blueprint: str | None = None) -> str:
    """A working title the person can change: the domain and the blueprint, or the opening words of the text when no blueprint fits."""
    if blueprint:
        return f"{domain + ': ' if domain else ''}{blueprint}"
    first = text.strip().split("\n")[0].split(". ")[0].strip(" .")
    return (first[:60].rstrip() + "...") if len(first) > 62 else first or "Untitled architecture"


async def reanalyse(n: int, text: str, domain: str | None) -> dict:
    d = _load(n)
    if d.get("submission"):
        raise BadRequest("This design has been submitted. Create a new design to analyse different requirements.")
    res = await analyse_text(text, domain)
    ext, rec = res["extraction"], res["recommendation"]
    d.update(requirement=dict(text=ext["text"]), extraction=ext, recommendation=rec, ai=res["ai"])
    if domain:
        d["domain"] = domain
    d["linked_apps"] = sorted(set(d["linked_apps"]) | {x["id"] for x in ext["systems"]})
    if not d.get("blueprint_id") and rec["recommended"]:
        _choose(d, rec["recommended"]["id"], overridden=False, reason="")
    _event(d, "Requirements re-analysed")
    _save(d)
    return view(n)


def _choose(d: dict, pid: str, overridden: bool, reason: str) -> None:
    if pid not in bp_gen.BLUEPRINTS:
        raise BadRequest(f"Unknown blueprint {pid}")
    s = reqs.suggest_selections(pid, d["extraction"])
    sel = engine.normalise_selections({**s["selections"], "personal_data": bool(d["extraction"].get("personal_data"))}, pid)
    d.update(blueprint_id=pid, blueprint_choice=dict(overridden=overridden, reason=reason, at=_now()), selections=sel, selection_sources=s["sources"], ops=[], decisions={}, validation=None)
    ext_nfr = d["extraction"]["nfr"]
    d["nfr"] = dict(ext_nfr)
    d["nfr_origin"] = {k: "from your requirements" for k in ext_nfr}
    _event(d, "Blueprint chosen", f"{pid}{' (different from the recommendation)' if overridden else ''}")


def choose_blueprint(n: int, pid: str, reason: str) -> dict:
    d = _load(n)
    if d.get("submission"):
        raise BadRequest("This design has been submitted. Create a new design to use a different blueprint.")
    rec = (d.get("recommendation") or {}).get("recommended")
    overridden = not rec or rec["id"] != pid
    if overridden and len((reason or "").strip()) < 5:
        raise BadRequest("Say briefly why you are choosing a different blueprint from the recommendation (5 characters or more).")
    _choose(d, pid, overridden, (reason or "").strip())
    _save(d)
    return view(n)


# ------------------------------------------------------------------ step 3 and 4: choices and edits
def update(n: int, patch: dict) -> dict:
    d = _load(n)
    if not d.get("blueprint_id"):
        raise BadRequest("Choose a blueprint first.")
    if "title" in patch and patch["title"] is not None:
        t = str(patch["title"]).strip()
        if len(t) < 3:
            raise BadRequest("The title needs at least 3 characters.")
        d["title"] = t[:120]
    for k in ("domain", "owner"):
        if patch.get(k) is not None:
            d[k] = str(patch[k]).strip()[:80]
    if patch.get("selections"):
        merged = {**d["selections"], **patch["selections"]}
        d["selections"] = engine.normalise_selections(merged, d["blueprint_id"])
        for k in patch["selections"]:
            d["selection_sources"][k] = "you"
        if "cloud" in patch["selections"] and "deployment" not in patch["selections"]:
            dep = d["selections"]["deployment"]
            if dep not in {x["id"] for x in cat.DEPLOYMENTS[d["selections"]["cloud"]]}:
                d["selections"]["deployment"] = cat.DEPLOYMENTS[d["selections"]["cloud"]][0]["id"]
                d["selection_sources"]["deployment"] = "changed with the cloud"
    if patch.get("nfr") is not None:
        nfr = dict(d["nfr"])
        for k, v in patch["nfr"].items():
            if v in (None, "", []):
                nfr.pop(k, None)
                d["nfr_origin"].pop(k, None)
            else:
                nfr[k] = v
                d["nfr_origin"][k] = "entered by you"
        d["nfr"] = engine.clean_nfr(nfr)
    if patch.get("linked_apps") is not None:
        ids = {a["id"] for a in get_store().apps}
        bad = [x for x in patch["linked_apps"] if x not in ids]
        if bad:
            raise BadRequest(f"Unknown application: {', '.join(bad)}")
        d["linked_apps"] = sorted(set(patch["linked_apps"]))
    engine.build(d["blueprint_id"], d["selections"], d["ops"])  # fail now, not on the next read
    _event(d, "Design changed", ", ".join(k for k in ("title", "domain", "selections", "nfr", "linked_apps") if patch.get(k) is not None))
    _save(d)
    return view(n)


def suggest_nfr(n: int) -> dict:
    d = _load(n)
    tier = d["selections"].get("tier", "tier2")
    for k, v in cat.TIER_NFR_DEFAULTS[tier].items():
        if k not in d["nfr"]:
            d["nfr"][k] = v
            d["nfr_origin"][k] = f"{tier} default, suggested"
    _event(d, "Targets suggested from the tier")
    _save(d)
    return view(n)


def set_ops(n: int, ops: list[dict]) -> dict:
    d = _load(n)
    if not d.get("blueprint_id"):
        raise BadRequest("Choose a blueprint first.")
    if len(ops) > MAX_OPS:
        raise BadRequest(f"A design can hold at most {MAX_OPS} edits.")
    before = engine.build(d["blueprint_id"], d["selections"], d["ops"])
    old = {repr(x["op"]) for x in before["skipped_ops"]}
    after = engine.build(d["blueprint_id"], d["selections"], ops)
    new_bad = [x for x in after["skipped_ops"] if repr(x["op"]) not in old]
    if new_bad:
        raise BadRequest(new_bad[0]["reason"])
    d["ops"] = ops
    _save(d)
    return view(n)


# ------------------------------------------------------------------ steps 5 and 6: validation and decisions
async def validate(n: int) -> dict:
    d = _load(n)
    arch, val = compute(d)
    if not val:
        raise BadRequest("Choose a blueprint first.")
    h = engine.inputs_hash(_inputs(d))
    d["validation"] = dict(hash=h, at=_now(), readiness=val["readiness"], verdict=val["verdict"], counts=val["open_counts"], coverage=val["coverage"]["percent"])
    _event(d, "Validated", f"readiness {val['readiness']}%, {val['verdict'].replace('_', ' ')}")
    _save(d)
    out = view(n)
    out["narration"] = await _narrate_validation(d, val)
    return out


async def _narrate_validation(d: dict, val: dict) -> dict:
    top = [g["title"] for g in val["gaps"] if g["state"] != "risk_accepted" and g["severity"] in ("critical", "high")][:3]
    facts = dict(title=d["title"], readiness=val["readiness"], verdict=val["verdict"].replace("_", " "), critical=val["open_counts"]["critical"], high=val["open_counts"]["high"], medium=val["open_counts"]["medium"], low=val["open_counts"]["low"],
                 assessed=val["coverage"]["assessed"], total=val["coverage"]["total"], top=top)
    return await narrate("studio.validation", facts, [("Run the standards engine", f"{val['standards']['passed']} passed, {val['standards']['failed']} failed", 300), ("Check NFR coverage", f"{val['nfr_coverage']['percent']}%", 160),
                                                      ("Check estate risk", f"{len(val['estate_risks'])} linked finding(s)", 200), ("Run the Studio checks", "lifecycle, structure, residency", 180)],
                         [("standard", g["standard_id"], g["title"]) for g in val["gaps"] if g.get("standard_id")][:6], 0.9)


def decide(n: int, gap_id: str, action: str, value: Any = None, note: str = "", alternative: int | None = None) -> dict:
    d = _load(n)
    arch, val = compute(d)
    gap = next((g for g in (val or {"gaps": []})["gaps"] if g["id"] == gap_id), None)
    decisions = d.setdefault("decisions", {})
    if action == "reopen":
        if gap_id not in decisions:
            raise BadRequest("There is no decision to reopen for this gap.")
        decisions.pop(gap_id)
        _event(d, "Decision reopened", gap_id)
        _save(d)
        return view(n)
    if not gap:
        raise NotFound(f"Gap {gap_id} is not open on this design. It may already be resolved.")
    if action == "risk_accept":
        if len((note or "").strip()) < 10:
            raise BadRequest("Accepting a risk needs a justification of at least 10 characters. It is recorded and sent to the review board.")
        decisions[gap_id] = dict(status="risk_accepted", note=note.strip()[:600], at=_now(), title=gap["title"], severity=gap["severity"])
        _event(d, "Risk accepted", f"{gap['title']}")
    elif action in ("accept", "modify"):
        fix = gap.get("fix")
        if not fix:
            raise BadRequest("This gap has no automatic recommendation. Edit the architecture or its choices, or accept the risk with a justification.")
        chosen = fix
        if alternative is not None:
            alts = fix.get("alternatives") or []
            if not (0 <= alternative < len(alts)):
                raise BadRequest("Unknown alternative.")
            chosen = alts[alternative]
        elif action == "modify" and not fix.get("input"):
            raise BadRequest("Choose one of the alternatives, or accept the recommendation as it is.")
        before_skipped = len(engine.build(d["blueprint_id"], d["selections"], d["ops"])["skipped_ops"])
        new = engine.apply_fix(_inputs(d), chosen, value)
        new["selections"] = engine.normalise_selections(new["selections"], d["blueprint_id"])
        new["nfr"] = engine.clean_nfr(new["nfr"])
        if len(engine.build(d["blueprint_id"], new["selections"], new["ops"])["skipped_ops"]) > before_skipped:
            raise BadRequest("That change cannot be applied to the architecture as it stands. Edit the diagram first.")
        _apply_inputs(d, new)
        for k in (chosen.get("nfr") or {}):
            d["nfr_origin"][k] = "recommendation accepted"
        if chosen.get("input") and chosen["input"]["field"].startswith("nfr."):
            d["nfr_origin"][chosen["input"]["field"].split(".", 1)[1]] = "entered by you"
        for k in list((chosen.get("selections_set") or {})) + ([chosen["input"]["field"].split(".", 1)[1]] if chosen.get("input") and chosen["input"]["field"].startswith("selections.") else []):
            d["selection_sources"][k] = "recommendation accepted"
        decisions[gap_id] = dict(status="modified" if alternative is not None else "accepted", fix_label=chosen["label"], value=value, at=_now(), title=gap["title"], severity=gap["severity"])
        _event(d, "Recommendation applied", chosen["label"])
    else:
        raise BadRequest("Action must be accept, modify, risk_accept or reopen.")
    _save(d)
    return view(n)


# ------------------------------------------------------------------ versions
def save_version(n: int, label: str) -> dict:
    d = _load(n)
    arch, val = compute(d)
    if not val:
        raise BadRequest("Choose a blueprint first.")
    vs = d.setdefault("versions", [])
    nxt = (vs[-1]["n"] + 1) if vs else 1
    snap = dict(n=nxt, at=_now(), label=(label or "").strip()[:80] or f"Version {nxt}", hash=engine.inputs_hash(_inputs(d)),
                summary=dict(readiness=val["readiness"], verdict=val["verdict"], open=val["open_counts"], coverage=val["coverage"]["percent"], components=len(arch["nodes"])),
                inputs=dict(_inputs(d), decisions=copy.deepcopy(d.get("decisions") or {}), nfr_origin=copy.deepcopy(d.get("nfr_origin") or {}), title=d["title"], domain=d.get("domain")))
    if vs:
        snap["changes"] = _changes(vs[-1]["inputs"], snap["inputs"])
    else:
        snap["changes"] = []
    vs.append(snap)
    if len(vs) > MAX_VERSIONS:
        del vs[0]
    _event(d, "Version saved", snap["label"])
    _save(d)
    return view(n)


def _changes(a: dict, b: dict) -> list[str]:
    out = []
    if a["blueprint_id"] != b["blueprint_id"]:
        out.append(f"Blueprint {a['blueprint_id']} to {b['blueprint_id']}")
    for k in sorted(set(a["selections"]) | set(b["selections"])):
        if a["selections"].get(k) != b["selections"].get(k):
            va, vb = a["selections"].get(k), b["selections"].get(k)
            if isinstance(va, list) and isinstance(vb, list):
                add, rem = sorted(set(vb) - set(va)), sorted(set(va) - set(vb))
                out.append(f"{k}: " + "; ".join(x for x in ((f"added {', '.join(add)}" if add else ""), (f"removed {', '.join(rem)}" if rem else "")) if x))
            else:
                out.append(f"{k}: {va} to {vb}")
    for k in sorted(set(a["nfr"]) | set(b["nfr"])):
        if a["nfr"].get(k) != b["nfr"].get(k):
            out.append(f"nfr {k}: {a['nfr'].get(k, 'not set')} to {b['nfr'].get(k, 'not set')}")
    if a["ops"] != b["ops"]:
        out.append(f"diagram edits: {len(a['ops'])} to {len(b['ops'])}")
    return out


def restore_version(n: int, vn: int) -> dict:
    d = _load(n)
    v = next((x for x in d.get("versions", []) if x["n"] == vn), None)
    if not v:
        raise NotFound(f"Version {vn} not found")
    inp = copy.deepcopy(v["inputs"])
    d.update(blueprint_id=inp["blueprint_id"], selections=inp["selections"], nfr=inp["nfr"], ops=inp["ops"], linked_apps=inp["linked_apps"], decisions=inp.get("decisions", {}), nfr_origin=inp.get("nfr_origin", {}))
    d["title"] = inp.get("title") or d["title"]
    _event(d, "Version restored", f"{v['label']}")
    _save(d)
    return view(n)


# ------------------------------------------------------------------ step 7: export
def _summary_facts(d: dict, arch: dict, val: dict) -> dict:
    sel = arch["selections"]
    pats = {p["id"]: p["name"] for p in get_store().patterns}
    top = [g["title"] for g in val["gaps"] if g["state"] != "risk_accepted"][:3]
    return dict(title=d["title"], blueprint=pats[arch["blueprint_id"]], cloud=next(c["label"] for c in cat.CLOUDS if c["id"] == sel["cloud"]), region=next(r["label"] for r in cat.REGIONS if r["id"] == sel["region"]),
                llm=(next((x["label"] for x in cat.LLMS if x["id"] == sel["llm"]), None) if any(nd["role"] == "ai_llm" for nd in arch["nodes"]) else None), readiness=val["readiness"], verdict=val["verdict"].replace("_", " "),
                open_count=sum(1 for g in val["gaps"] if g["state"] != "risk_accepted"), top=top)


async def document(n: int) -> dict:
    d = _load(n)
    arch, val = compute(d)
    if not arch:
        raise BadRequest("Choose a blueprint first.")
    ai = await narrate("studio.summary", _summary_facts(d, arch, val), [("Collect results", "validation and gaps", 120), ("Write the summary", "from the computed figures only", 200)], [("pattern", arch["blueprint_id"], d["title"])], 0.88)
    d2 = dict(d, nfr_origin=d.get("nfr_origin"))
    md = export.document(d2, arch, val, ai["summary"])
    return dict(markdown=md, filename=f"{export.slug(d['title'])}-target-architecture.md", ai=ai)


def export_preview(d: dict, arch: dict, val: dict) -> dict:
    pack = export.starter(dict(d), arch, val, "(document included in the ZIP)")
    return dict(root=pack["root"], manifest=pack["manifest"], checks=pack["checks"], passed=pack["passed"], failed=pack["failed"], not_run=pack["not_run"], notes=pack["notes"])


async def starter_zip(n: int) -> tuple[bytes, str]:
    d = _load(n)
    arch, val = compute(d)
    if not arch:
        raise BadRequest("Choose a blueprint first.")
    doc = await document(n)
    pack = export.starter(dict(d), arch, val, doc["markdown"])
    d.setdefault("exports", []).append(dict(at=_now(), kind="starter.zip", files=len(pack["files"]), checks_failed=pack["failed"]))
    d["exports"] = d["exports"][-20:]
    _event(d, "Starter ZIP generated", f"{len(pack['files'])} files, {pack['failed']} failed checks")
    _save(d)
    return export.zip_bytes(pack), f"{pack['root']}-starter.zip"


def diagram(n: int, kind: str) -> tuple[str, str, str]:
    d = _load(n)
    arch, _ = compute(d)
    if not arch:
        raise BadRequest("Choose a blueprint first.")
    base = export.slug(d["title"])
    if kind == "svg":
        return export.svg(arch, d["title"]), "image/svg+xml", f"{base}.svg"
    return export.mermaid(arch), "text/plain", f"{base}.mmd"


# ------------------------------------------------------------------ step 8: governance
def submission_checks(d: dict, val: dict) -> list[dict]:
    open_ = [g for g in val["gaps"] if g["state"] != "risk_accepted"]
    crit = [g for g in open_ if g["severity"] == "critical"]
    high = [g for g in open_ if g["severity"] == "high"]
    checks = [
        dict(id="title", label="The design has a title and a business domain", ok=bool(d["title"].strip()) and bool((d.get("domain") or "").strip()), blocking=True, detail="Set both in the Customise step." if not (d.get("domain") or "").strip() else ""),
        dict(id="requirements", label="The requirements are recorded", ok=len((d.get("requirement") or {}).get("text", "")) >= 20, blocking=True, detail=""),
        dict(id="critical", label="No critical gap is open", ok=not crit, blocking=True, detail=("; ".join(g["title"] for g in crit[:3]) + ". Fix them, or accept the risk with a justification.") if crit else ""),
        dict(id="high", label="High gaps travel with the submission as conditions", ok=not high, blocking=False, detail=f"{len(high)} high gap(s) will be listed as conditions for the board." if high else ""),
        dict(id="coverage", label="At least 70% of the components could be assessed", ok=val["coverage"]["percent"] >= engine.COVERAGE_FLOOR, blocking=False, detail=f"{val['coverage']['percent']}% assessed. The board will see the unassessed components listed." if val["coverage"]["percent"] < engine.COVERAGE_FLOOR else ""),
        dict(id="nfr", label="All six required non-functional targets are stated", ok=not val["nfr_coverage"]["missing"], blocking=False, detail=("Missing: " + ", ".join(k.replace("_", " ") for k in val["nfr_coverage"]["missing"])) if val["nfr_coverage"]["missing"] else ""),
    ]
    return checks


def _next_arb_id() -> str:
    nums = []
    for a in review_engine.all_submissions():
        try:
            nums.append(int(a["id"].rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return f"ARB-{date.today().year}-{(max(nums) if nums else 0) + 1:03d}"


async def submit(n: int, notes: str, submitter: str | None) -> dict:
    d = _load(n)
    arch, val = compute(d)
    if not val:
        raise BadRequest("Choose a blueprint first.")
    checks = submission_checks(d, val)
    blockers = [c for c in checks if c["blocking"] and not c["ok"]]
    if blockers:
        raise BadRequest("Cannot submit yet: " + "; ".join(c["label"] + (f" ({c['detail']})" if c["detail"] else "") for c in blockers))
    h = engine.inputs_hash(_inputs(d))
    prev = d.get("submission")
    if prev and prev["hash"] == h:
        raise BadRequest(f"This version was already submitted as {prev['arb_id']}. Change the design to submit a new version.")
    d["validation"] = dict(hash=h, at=_now(), readiness=val["readiness"], verdict=val["verdict"], counts=val["open_counts"], coverage=val["coverage"]["percent"])
    # keep an immutable record of exactly what was submitted
    d.setdefault("versions", [])
    nxt = (d["versions"][-1]["n"] + 1) if d["versions"] else 1
    vs = d["versions"]
    snap = dict(n=nxt, at=_now(), label=f"Submitted for review ({prev['arb_id'] + ' resubmission' if prev else 'first submission'})", hash=h,
                summary=dict(readiness=val["readiness"], verdict=val["verdict"], open=val["open_counts"], coverage=val["coverage"]["percent"], components=len(arch["nodes"])),
                inputs=dict(_inputs(d), decisions=copy.deepcopy(d.get("decisions") or {}), nfr_origin=copy.deepcopy(d.get("nfr_origin") or {}), title=d["title"], domain=d.get("domain")))
    snap["changes"] = _changes(vs[-1]["inputs"], snap["inputs"]) if vs else []
    vs.append(snap)
    comps = engine.components_of(arch)
    accepted = [dict(gap=g["title"], note=g["decision"]["note"], severity=g["severity"]) for g in val["gaps"] if g["state"] == "risk_accepted"]
    payload = dict(title=d["title"], domain=d.get("domain") or "", submitter=(submitter or d.get("owner") or "You").strip()[:80], stage="ai_reviewed", submitted_at=date.today().isoformat(), arb_date="", tier=d["selections"].get("tier", "tier2"),
                   summary=(d["requirement"]["text"][:240] + ("..." if len(d["requirement"]["text"]) > 240 else "")), nfr=d["nfr"], components=comps, submitter_id=None, linked_apps=val["inputs"]["linked_apps"], source="studio", design_id=n,
                   design_ref=d["ref"], design_version=nxt, blueprint_id=arch["blueprint_id"], notes=(notes or "").strip()[:1000], conditions=val["conditions"], accepted_risks=accepted, history=[])
    if prev:
        row = next((r for r in persist.list_items(SUBMISSION_KIND, 500) if r["arb_id"] == prev["arb_id"]), None)
        arb_id = prev["arb_id"]
        if row:
            hist = list(row.get("history", [])) + [dict(at=_now(), version=row["design_version"], stage=row["stage"], readiness=prev.get("readiness"))]
            payload.update(arb_id=arb_id, history=hist[-30:])
            persist.update_item(SUBMISSION_KIND, row["id"], payload)
        else:
            payload["arb_id"] = arb_id
            persist.add_item(SUBMISSION_KIND, payload)
    else:
        arb_id = _next_arb_id()
        payload["arb_id"] = arb_id
        persist.add_item(SUBMISSION_KIND, payload)
    d["submission"] = dict(arb_id=arb_id, submitted_at=_now(), version=nxt, stage="ai_reviewed", hash=h, readiness=val["readiness"], verdict=val["verdict"], conditions=len(val["conditions"]), notes=payload["notes"])
    _event(d, "Submitted to the architecture review board" if not prev else "Resubmitted to the architecture review board", f"{arb_id}, version {nxt}")
    _save(d)
    out = view(n)
    out["narration"] = await narrate("studio.submission", dict(title=d["title"], arb_id=arb_id, stage="ai reviewed", readiness=val["readiness"], conditions=len(val["conditions"])), [("Check submission rules", f"{len(checks)} checks", 120), ("Record version", f"version {nxt}", 100),
                                                                                                                                                                     ("Enter the review queue", arb_id, 140)], [("review", arb_id, d["title"])], 0.9)
    return out
